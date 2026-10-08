// The two recorders: what a process (Teams and its children) plays, via WASAPI process
// loopback; and the microphone, via WASAPI capture that follows the default input device.
using System.Diagnostics;
using System.Runtime.InteropServices;
using NAudio.CoreAudioApi;
using NAudio.CoreAudioApi.Interfaces;
using NAudio.Wave;

namespace TeamsTap;

internal interface IRecorder
{
    void Start();
    void Stop();
}

/// Captures the audio rendered by `pid` and (by default) its descendants. Windows resolves the
/// process tree itself, so Teams' helper processes are included without enumerating them.
internal sealed class ProcessTapRecorder : IRecorder
{
    // The audio engine converts to this format (AUTOCONVERTPCM): 16-bit PCM by default, or 32-bit float.
    private readonly WaveFormat CaptureFormat;
    private const long BufferDuration100ns = 2_000_000;                     // 200 ms

    private readonly uint _pid;
    private readonly string _path;
    private readonly bool _includeTree;
    private readonly double? _epoch;
    private readonly double _waitAudioSeconds;
    private AudioClient? _client;
    private Timeline? _timeline;
    private Thread? _thread;
    private readonly ManualResetEvent _stopEvent = new(false);
    private readonly AutoResetEvent _dataEvent = new(false);
    private bool _stopped;

    public ProcessTapRecorder(uint pid, string path, bool includeTree, double? epoch, double waitAudioSeconds, int bits)
    {
        CaptureFormat = bits == 32 ? WaveFormat.CreateIeeeFloatWaveFormat(48000, 2) : new WaveFormat(48000, 16, 2);
        _pid = pid; _path = path; _includeTree = includeTree; _epoch = epoch; _waitAudioSeconds = waitAudioSeconds;
    }

    public void Start()
    {
        if (!ProcessAlive(_pid)) Program.Fail($"process {_pid} does not exist");
        IAudioClient iface = ActivateWithRetry();
        _client = new AudioClient(iface);
        _client.Initialize(
            AudioClientShareMode.Shared,
            AudioClientStreamFlags.Loopback | AudioClientStreamFlags.EventCallback | AudioClientStreamFlags.AutoConvertPcm | AudioClientStreamFlags.SrcDefaultQuality,
            BufferDuration100ns, 0, CaptureFormat, Guid.Empty);
        _client.SetEventHandle(_dataEvent.SafeWaitHandle.DangerousGetHandle());
        _timeline = new Timeline(_path, CaptureFormat, _epoch);
        var capture = _client.AudioCaptureClient;
        _client.Start();
        _thread = new Thread(() => CaptureLoop(capture)) { IsBackground = true, Name = "teams-tap capture" };
        _thread.Start();
        Program.Log($"capturing process {_pid}{(_includeTree ? " and its descendants" : "")}");
        Program.Log($"recording process {_pid} to {_path}");
    }

    /// Activation can fail while the target is still starting its audio; retry for --wait-audio seconds.
    private IAudioClient ActivateWithRetry()
    {
        var deadline = DateTime.UtcNow.AddSeconds(_waitAudioSeconds);
        while (true)
        {
            try { return Native.ActivateProcessLoopbackAsync(_pid, _includeTree).GetAwaiter().GetResult(); }
            catch (Exception ex) when (DateTime.UtcNow < deadline && ProcessAlive(_pid))
            {
                Program.Verbose($"process loopback activation failed ({ex.Message}); retrying");
                Thread.Sleep(500);
            }
            catch (Exception ex) { Program.Fail($"could not capture process {_pid}: {ex.Message}"); throw; }
        }
    }

    private void CaptureLoop(AudioCaptureClient capture)
    {
        var handles = new WaitHandle[] { _dataEvent, _stopEvent };
        int blockAlign = CaptureFormat.BlockAlign;
        byte[] buffer = new byte[CaptureFormat.AverageBytesPerSecond];
        while (true)
        {
            if (WaitHandle.WaitAny(handles, 500) == 1) break;
            try
            {
                for (int packet = capture.GetNextPacketSize(); packet > 0; packet = capture.GetNextPacketSize())
                {
                    IntPtr data = capture.GetBuffer(out int frames, out AudioClientBufferFlags flags, out long _, out long qpc100ns);
                    int bytes = frames * blockAlign;
                    if (buffer.Length < bytes) buffer = new byte[bytes];
                    if ((flags & AudioClientBufferFlags.Silent) != 0) Array.Clear(buffer, 0, bytes);
                    else Marshal.Copy(data, buffer, 0, bytes);
                    double? host = (flags & AudioClientBufferFlags.TimestampError) == 0 && qpc100ns > 0
                        ? qpc100ns / 1e7
                        : Timeline.NowSeconds() - frames / (double)CaptureFormat.SampleRate;
                    _timeline!.Write(buffer, bytes, host);
                    capture.ReleaseBuffer(frames);
                }
            }
            catch (Exception ex) { Program.Log($"error reading captured audio: {ex.Message}"); }
        }
    }

    public void Stop()
    {
        if (_stopped) return;
        _stopped = true;
        _stopEvent.Set();
        _thread?.Join(TimeSpan.FromSeconds(5));
        try { _client?.Stop(); } catch { /* already stopped */ }
        _timeline?.Finish();                    // pad the tail up to the stop instant
        Program.Log("stopped, " + (_timeline?.Summary ?? "nothing written"));
        _timeline?.Dispose();
        _client?.Dispose();
    }

    public static bool ProcessAlive(uint pid)
    {
        try { using var p = Process.GetProcessById((int)pid); return !p.HasExited; }
        catch { return false; }
    }
}

/// Records the microphone to 48 kHz mono WAV (16-bit PCM or 32-bit float, see --bits). Follows the default input device: when the
/// user switches to a headset (or the device disappears) capture restarts on the new default,
/// and the shared timeline keeps the file continuous.
internal sealed class MicRecorder : IRecorder, IMMNotificationClient
{
    private readonly WaveFormat OutFormat;   // 48 kHz mono: 16-bit PCM by default, or 32-bit float

    private readonly string _deviceName;
    private readonly string _path;
    private readonly double? _epoch;
    private readonly MMDeviceEnumerator _enumerator = new();
    private readonly object _gate = new();
    private WasapiCapture? _capture;
    private Timeline? _timeline;
    private Converter? _converter;
    private int _restarts;
    private volatile bool _stopping;

    public MicRecorder(string deviceName, string path, double? epoch, int bits)
    {
        OutFormat = bits == 32 ? WaveFormat.CreateIeeeFloatWaveFormat(48000, 1) : new WaveFormat(48000, 16, 1);
        _deviceName = deviceName; _path = path; _epoch = epoch;
    }

    public void Start()
    {
        _timeline = new Timeline(_path, OutFormat, _epoch);
        if (IsDefault) _enumerator.RegisterEndpointNotificationCallback(this);
        StartCapture(initial: true);
        Program.Log($"recording microphone ({_deviceName}) to {_path}");
    }

    private bool IsDefault => _deviceName.Equals("default", StringComparison.OrdinalIgnoreCase);

    private MMDevice SelectDevice()
    {
        if (!IsDefault)
        {
            foreach (var d in _enumerator.EnumerateAudioEndPoints(DataFlow.Capture, DeviceState.Active))
                if (d.FriendlyName.Equals(_deviceName, StringComparison.OrdinalIgnoreCase) || d.DeviceFriendlyName.Equals(_deviceName, StringComparison.OrdinalIgnoreCase))
                    return d;
            Program.Log($"microphone '{_deviceName}' not found; using the default input");
        }
        return _enumerator.GetDefaultAudioEndpoint(DataFlow.Capture, Role.Console);
    }

    private void StartCapture(bool initial)
    {
        lock (_gate)
        {
            if (_stopping) return;
            MMDevice device;
            try { device = SelectDevice(); }
            catch (Exception ex)
            {
                if (initial) Program.Fail($"no microphone available (missing device or permission denied): {ex.Message}");
                Program.Log($"no input device available ({ex.Message}); retrying in 1 s");
                ThreadPool.QueueUserWorkItem(_ => { Thread.Sleep(1000); StartCapture(false); });
                return;
            }
            var capture = new WasapiCapture(device, true, 100);
            _converter = new Converter(capture.WaveFormat, OutFormat.SampleRate, OutFormat.BitsPerSample);
            capture.DataAvailable += OnData;
            capture.RecordingStopped += OnStopped;
            Program.Verbose($"microphone: {device.FriendlyName}, {capture.WaveFormat}");
            try { capture.StartRecording(); }
            catch (Exception ex)
            {
                capture.Dispose();
                if (initial) Program.Fail($"could not start microphone capture: {ex.Message}");
                Program.Log($"could not restart microphone ({ex.Message}); retrying in 1 s");
                ThreadPool.QueueUserWorkItem(_ => { Thread.Sleep(1000); StartCapture(false); });
                return;
            }
            _capture = capture;
        }
    }

    private void OnData(object? sender, WaveInEventArgs e)
    {
        var converter = _converter;
        if (converter == null || e.BytesRecorded == 0 || !ReferenceEquals(sender, _capture)) return;
        byte[] samples = converter.Convert(e.Buffer, e.BytesRecorded, out int frames);
        if (frames == 0) return;
        double host = Timeline.NowSeconds() - frames / (double)OutFormat.SampleRate;
        _timeline!.Write(samples, frames * OutFormat.BlockAlign, host);
    }

    private void OnStopped(object? sender, StoppedEventArgs e)
    {
        if (_stopping || !ReferenceEquals(sender, _capture)) return;
        Restart(e.Exception?.Message ?? "capture stopped");
    }

    private void Restart(string reason)
    {
        if (_stopping) return;
        Interlocked.Increment(ref _restarts);
        Program.Log($"audio configuration changed ({_restarts}): {reason}; restarting microphone capture");
        ThreadPool.QueueUserWorkItem(_ =>
        {
            lock (_gate)
            {
                var old = _capture; _capture = null;
                try { old?.StopRecording(); } catch { }
                old?.Dispose();
            }
            StartCapture(false);
        });
    }

    // IMMNotificationClient: follow the default input device.
    public void OnDefaultDeviceChanged(DataFlow flow, Role role, string defaultDeviceId)
    {
        if (flow == DataFlow.Capture && role == Role.Console) Restart("default input changed");
    }
    public void OnDeviceStateChanged(string deviceId, DeviceState newState) { }
    public void OnDeviceAdded(string pwstrDeviceId) { }
    public void OnDeviceRemoved(string deviceId) { }
    public void OnPropertyValueChanged(string pwstrDeviceId, PropertyKey key) { }

    public void Stop()
    {
        if (_stopping) return;
        _stopping = true;
        if (IsDefault) { try { _enumerator.UnregisterEndpointNotificationCallback(this); } catch { } }
        lock (_gate)
        {
            try { _capture?.StopRecording(); } catch { }
            _capture?.Dispose();
            _capture = null;
        }
        _timeline?.Finish();
        Program.Log($"microphone stopped, {_timeline?.Summary ?? "nothing written"}, {_restarts} restart(s)");
        _timeline?.Dispose();
    }

    /// Converts the device's native format (float or integer PCM, any channel count and rate)
    /// to mono at the output rate and bit depth, with a linear resampler that keeps state across chunks.
    private sealed class Converter
    {
        private readonly int _channels, _bits, _inRate, _outRate, _outBits;
        private readonly bool _isFloat;
        private double _pos;          // fractional read position into the current chunk
        private float _last;          // last input sample of the previous chunk

        public Converter(WaveFormat inFormat, int outRate, int outBits)
        {
            _outBits = outBits;
            _channels = inFormat.Channels; _bits = inFormat.BitsPerSample; _inRate = inFormat.SampleRate; _outRate = outRate;
            _isFloat = inFormat.Encoding == WaveFormatEncoding.IeeeFloat
                || (inFormat is WaveFormatExtensible ext && ext.SubFormat == NAudio.Dmo.AudioMediaSubtypes.MEDIASUBTYPE_IEEE_FLOAT);
        }

        public byte[] Convert(byte[] buffer, int count, out int outFrames)
        {
            int bytesPerSample = _bits / 8, frameBytes = bytesPerSample * _channels, inFrames = count / frameBytes;
            var mono = new float[inFrames];
            for (int f = 0; f < inFrames; f++)
            {
                float sum = 0;
                for (int c = 0; c < _channels; c++) sum += Sample(buffer, f * frameBytes + c * bytesPerSample);
                mono[f] = sum / _channels;
            }
            float[] output;
            if (_inRate == _outRate) output = mono;
            else
            {
                double step = _inRate / (double)_outRate;
                var list = new List<float>(inFrames * _outRate / _inRate + 2);
                // _pos indexes this chunk; -1 is the last sample of the previous chunk (_last)
                while (_pos <= inFrames - 1)
                {
                    int i = (int)Math.Floor(_pos);
                    float a = i < 0 ? _last : mono[i];
                    float b = i + 1 < inFrames ? mono[i + 1] : mono[inFrames - 1];
                    double frac = _pos - i;
                    list.Add((float)(a + (b - a) * frac));
                    _pos += step;
                }
                _pos -= inFrames;
                if (inFrames > 0) _last = mono[inFrames - 1];
                output = list.ToArray();
            }
            outFrames = output.Length;
            if (_outBits == 16)
            {
                var pcm = new byte[output.Length * 2];
                for (int i = 0; i < output.Length; i++)
                {
                    short v = (short)Math.Round(Math.Clamp(output[i], -1f, 1f) * short.MaxValue);
                    pcm[2 * i] = (byte)v;
                    pcm[2 * i + 1] = (byte)(v >> 8);
                }
                return pcm;
            }
            var bytes = new byte[output.Length * 4];
            Buffer.BlockCopy(output, 0, bytes, 0, bytes.Length);
            return bytes;
        }

        private float Sample(byte[] b, int offset) => (_isFloat, _bits) switch
        {
            (true, 32) => BitConverter.ToSingle(b, offset),
            (false, 16) => BitConverter.ToInt16(b, offset) / 32768f,
            (false, 24) => ((b[offset] | b[offset + 1] << 8 | (sbyte)b[offset + 2] << 16)) / 8388608f,
            (false, 32) => BitConverter.ToInt32(b, offset) / 2147483648f,
            _ => 0f,
        };
    }
}
