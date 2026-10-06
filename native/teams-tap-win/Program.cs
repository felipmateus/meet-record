// teams-tap for Windows: same command-line contract as the macOS tool (native/teams-tap),
// so the Python adapters can drive either one.
//
//   teams-tap --pid <pid> --out <file.wav> [--epoch <unix s>] [--wait-audio <s>] [--stop-file <path>] [--no-descendants] [--verbose]
//       Records what process <pid> and its descendants play (WASAPI process loopback,
//       Windows 10 2004 / build 19041 or later). 48 kHz 16-bit stereo PCM.
//   teams-tap --mic <default|name> --out <file.wav> [--epoch <unix s>] [--stop-file <path>] [--verbose]
//       Records the microphone to 48 kHz mono float, following the default input device.
//   teams-tap --list
//       Lists the processes that have audio sessions on output devices (pid, parent, active?, exe).
//
// Stop: Ctrl+C / Ctrl+Break (CTRL_BREAK_EVENT from a parent that started us in a new process
// group), the line "stop" on stdin, or the file given by --stop-file appearing (works from any
// process, e.g. `trec stop` stopping a recorder that `trec start` launched). In tap mode it also stops when the target process exits.
// Time without audio is written as silence, so the file length equals wall time (see Timeline).
using NAudio.CoreAudioApi;

namespace TeamsTap;

internal static class Program
{
    private static bool _verbose;
    private static readonly ManualResetEventSlim Done = new(false);

    public static void Log(string message) => Console.Error.WriteLine("teams-tap: " + message);
    public static void Verbose(string message) { if (_verbose) Log(message); }

    public static void Fail(string message, int code = 1)
    {
        Log(message);
        Environment.Exit(code);
    }

    private static int Main(string[] argv)
    {
        if (!OperatingSystem.IsWindowsVersionAtLeast(10, 0, 19041))
            Fail("requires Windows 10 version 2004 (build 19041) or later");

        uint pid = 0;
        string? output = null, mic = null, stopFile = null;
        double? epoch = null;
        double waitAudio = 20;
        bool list = false, includeTree = true;

        for (int i = 0; i < argv.Length; i++)
        {
            string a = argv[i];
            string Next(string what) => i + 1 < argv.Length ? argv[++i] : throw new ArgumentException($"{a} requires {what}");
            try
            {
                switch (a)
                {
                    case "--pid": pid = uint.Parse(Next("a number")); break;
                    case "--out": output = Next("a path"); break;
                    case "--epoch": epoch = double.Parse(Next("Unix seconds"), System.Globalization.CultureInfo.InvariantCulture); break;
                    case "--wait-audio": waitAudio = double.Parse(Next("seconds"), System.Globalization.CultureInfo.InvariantCulture); break;
                    case "--mic": mic = Next("'default' or a device name"); break;
                    case "--stop-file": stopFile = Next("a path"); break;
                    case "--no-descendants": includeTree = false; break;
                    case "--list": list = true; break;
                    case "--verbose": case "-v": _verbose = true; break;
                    case "--help": case "-h": PrintUsage(); return 0;
                    default: Fail($"unknown argument: {a}"); break;
                }
            }
            catch (Exception ex) when (ex is FormatException or ArgumentException or OverflowException)
            {
                Fail(ex is ArgumentException ? ex.Message : $"invalid value for {a}");
            }
        }

        if (list) { ListAudioProcesses(); return 0; }
        if (output == null) Fail("--out is required");
        if (mic == null && pid == 0) Fail("--pid is required");

        if (stopFile != null) { try { File.Delete(stopFile); } catch (IOException) { } }   // a stale file must not stop us at once
        IRecorder recorder = mic != null
            ? new MicRecorder(mic, output!, epoch)
            : new ProcessTapRecorder(pid, output!, includeTree, epoch, waitAudio);
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; Done.Set(); };   // before Start, so Ctrl+C never skips finalizing the WAV
        recorder.Start();

        new Thread(() =>
        {
            // "stop" on stdin; EOF is ignored (parents may start us with stdin closed)
            string? line;
            while ((line = Console.In.ReadLine()) != null)
                if (line.Trim().Equals("stop", StringComparison.OrdinalIgnoreCase)) { Done.Set(); return; }
        }) { IsBackground = true }.Start();
        if (stopFile != null)
        {
            new Thread(() =>
            {
                while (!Done.IsSet)
                {
                    if (File.Exists(stopFile)) { Verbose($"stop file {stopFile} found"); Done.Set(); return; }
                    Thread.Sleep(200);
                }
            }) { IsBackground = true }.Start();
        }
        if (mic == null)
        {
            new Thread(() =>
            {
                while (!Done.IsSet)
                {
                    if (!ProcessTapRecorder.ProcessAlive(pid)) { Log($"process {pid} exited"); Done.Set(); return; }
                    Thread.Sleep(1000);
                }
            }) { IsBackground = true }.Start();
        }

        Done.Wait();
        recorder.Stop();
        return 0;
    }

    private static void PrintUsage()
    {
        Console.WriteLine("Usage: teams-tap --pid <pid> --out <file.wav> [--epoch <unix s>] [--wait-audio <s>] [--stop-file <path>] [--no-descendants] [--verbose]");
        Console.WriteLine("       teams-tap --mic <default|name> --out <file.wav> [--epoch <unix s>] [--stop-file <path>] [--verbose]   records the microphone (48 kHz mono), following the default input");
        Console.WriteLine("       teams-tap --list        lists the processes with audio sessions on output devices (pid, parent, active?, exe)");
        Console.WriteLine("       --epoch aligns the file to a shared start instant; time without audio is written as silence");
        Console.WriteLine("       stop with Ctrl+C / Ctrl+Break, the line \"stop\" on stdin, or by creating the --stop-file");
    }

    private static void ListAudioProcesses()
    {
        var table = Native.ProcessTable();
        var seen = new HashSet<uint>();
        Console.WriteLine("pid\tppid\temitting\tbundle");
        using var enumerator = new MMDeviceEnumerator();
        foreach (var device in enumerator.EnumerateAudioEndPoints(DataFlow.Render, DeviceState.Active))
        {
            var sessions = device.AudioSessionManager.Sessions;
            for (int i = 0; i < sessions.Count; i++)
            {
                var s = sessions[i];
                uint id = s.GetProcessID;
                if (id == 0 || !seen.Add(id)) continue;
                bool active = s.State == NAudio.CoreAudioApi.Interfaces.AudioSessionState.AudioSessionStateActive;
                var (parent, exe) = table.TryGetValue(id, out var info) ? info : (0u, "");
                Console.WriteLine($"{id}\t{parent}\t{(active ? "yes" : "no")}\t{exe}");
            }
        }
    }
}
