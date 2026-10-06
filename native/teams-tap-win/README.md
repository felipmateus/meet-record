# teams-tap for Windows

`teams-tap.exe` is the Windows counterpart of the macOS `native/teams-tap` binary. It keeps the same command-line contract so the Python adapters can drive either one. It is a C# .NET 8 console app using NAudio for WASAPI, published as a self-contained single-file x64 executable (no .NET install needed on the target machine).

**Status:** compiles, not yet tested on a Windows machine. The Python side (adapters, detector, scheduler) is still macOS-only; see "Not done yet" below.

## Build

```bash
scripts/build-native-windows.sh     # from macOS/Linux, needs the .NET 8 SDK (brew install dotnet@8)
```

```powershell
scripts\build-native-windows.ps1    # on Windows, needs the .NET 8 SDK (winget install Microsoft.DotNet.SDK.8)
```

Output: `native/teams-tap-win/bin/Release/net8.0/win-x64/publish/teams-tap.exe`.

## Requirements

Windows 10 version 2004 (build 19041) or later, or Windows 11. Process loopback capture does not exist on earlier builds. Microphone access must be allowed for desktop apps (Settings > Privacy & security > Microphone).

## Usage

```text
teams-tap --pid <pid> --out <file.wav> [--epoch <unix s>] [--wait-audio <s>] [--no-descendants] [--verbose]
teams-tap --mic <default|name> --out <file.wav> [--epoch <unix s>] [--verbose]
teams-tap --list
```

- `--pid` records what the process plays, plus its whole process tree (Windows resolves the tree, so the `ms-teams.exe` helper processes are included). Output is 48 kHz 16-bit stereo PCM. `--no-descendants` captures everything except that tree instead, which is only useful for diagnosis. `--wait-audio` retries activation for that many seconds while the target is starting (default 20).
- `--mic` records the microphone to 48 kHz mono float. `default` follows the Windows default input device and restarts capture when it changes. Any other value is matched against the device's friendly name.
- `--list` prints the processes that have audio sessions on output devices, as `pid`, `ppid`, `emitting` (session active) and the executable name.
- `--epoch` aligns the file to a shared start instant. Time without audio is written as silence, so tracks stay aligned and the file length matches wall time. Gaps are logged on stderr as `gap of X s at Y s`.

## Stopping

Windows has no SIGTERM, so the recorder stops on any of:

- Ctrl+C or Ctrl+Break in its console. A parent process should start it with `CREATE_NEW_PROCESS_GROUP` and send `CTRL_BREAK_EVENT`.
- The line `stop` on stdin. A parent should start it with a stdin pipe and write `stop\n`. End of input is ignored.
- In `--pid` mode, the target process exiting (`process <pid> exited`).

In every case the file is padded to the stop instant, the WAV header is finalized and the process exits with code 0.

## Not done yet

- Windows Python adapters (`capture_wasapi`, `capture_mic_wasapi`) that spawn this binary and stop it with `stop` on stdin.
- A call detector (for example, an active capture session of `ms-teams.exe` on the microphone instead of `pmset` assertions).
- Task Scheduler instead of launchd, Windows toast notifications, and `ffmpeg`/`whisper-cli` paths for Windows.
