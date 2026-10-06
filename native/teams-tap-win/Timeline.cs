// Same contract as TimelineWriter in the macOS teams-tap: every chunk is written at its
// time position relative to a shared --epoch; missing time becomes silence and is logged,
// and Finish() pads the tail up to the stop instant. Keeps the Teams and microphone tracks
// aligned and with the real call duration even when the audio stack pauses delivery.
using System.Diagnostics;
using NAudio.Wave;

namespace TeamsTap;

internal sealed class Timeline : IDisposable
{
    private const double MinPadSeconds = 0.2;   // jitter below this is ignored
    private const double LogGapSeconds = 0.5;   // gaps from this size up are logged

    private readonly WaveFileWriter _writer;
    private readonly WaveFormat _format;
    private readonly double _startSeconds;      // QPC time when this writer started
    private readonly double _epochOffset;       // seconds from --epoch to this writer's start
    private readonly object _lock = new();
    private long _framesWritten;
    private double _paddedSeconds;
    private int _gaps;

    public Timeline(string path, WaveFormat format, double? epoch)
    {
        _writer = new WaveFileWriter(path, format);
        _format = format;
        _startSeconds = NowSeconds();
        _epochOffset = epoch.HasValue ? Math.Max(0, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0 - epoch.Value) : 0;
    }

    public static double NowSeconds() => Stopwatch.GetTimestamp() / (double)Stopwatch.Frequency;

    private int BytesPerFrame => _format.BlockAlign;

    private long ExpectedFrame(double hostSeconds) =>
        (long)((_epochOffset + Math.Max(0, hostSeconds - _startSeconds)) * _format.SampleRate);

    /// Writes `count` bytes whose first sample was captured at `hostSeconds` (QPC seconds), if known.
    public void Write(byte[] data, int count, double? hostSeconds)
    {
        lock (_lock)
        {
            if (hostSeconds.HasValue) PadLocked(ExpectedFrame(hostSeconds.Value));
            _writer.Write(data, 0, count);
            _framesWritten += count / BytesPerFrame;
        }
    }

    public void Finish()
    {
        lock (_lock) { PadLocked(ExpectedFrame(NowSeconds())); _writer.Flush(); }
    }

    private void PadLocked(long target)
    {
        long missing = target - _framesWritten;
        double seconds = missing / (double)_format.SampleRate;
        if (seconds < MinPadSeconds) return;
        double at = _framesWritten / (double)_format.SampleRate;
        if (_framesWritten == 0) Program.Log($"start offset {seconds:F1} s (padded with silence)");
        else if (seconds >= LogGapSeconds) { _gaps++; _paddedSeconds += seconds; Program.Log($"gap of {seconds:F1} s at {at:F1} s (padded with silence)"); }
        var silence = new byte[_format.SampleRate * BytesPerFrame];   // one second per write
        while (missing > 0)
        {
            int frames = (int)Math.Min(_format.SampleRate, missing);
            _writer.Write(silence, 0, frames * BytesPerFrame);
            _framesWritten += frames;
            missing -= frames;
        }
    }

    public string Summary =>
        $"{_framesWritten / (double)_format.SampleRate:F1} s written, {_gaps} gap(s), {_paddedSeconds:F1} s of silence padded";

    public void Dispose() => _writer.Dispose();
}
