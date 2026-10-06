# Installs teams-recorder on this Windows PC, from a clone of the repository. Safe to run again:
# every step checks what is already there and only does what is missing.
#
#   scripts\install.ps1 [-Name "Your name"] [-Provider claude-code|api] [-SkipModel] [-NoAgent] [-Yes] [-DryRun]
#
# Steps: check Windows (10 2004+ / 11) and Teams, winget packages (Python 3.12, ffmpeg, .NET 8 SDK
# when teams-tap.exe must be built), whisper.cpp into tools\whisper, the Python virtualenv,
# teams-tap.exe, config.toml ([user] name, llm provider), .env (API provider only), the whisper
# model, trec doctor, the scheduled tasks (daemon at logon + 6 pm planner) and the microphone
# privacy setting. Logging in to Claude Code is left to you (it needs your browser).
param(
    [string]$Name = "",
    [ValidateSet("", "claude-code", "api")][string]$Provider = "",
    [switch]$SkipModel,
    [switch]$NoAgent,
    [switch]$Yes,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $ProjectDir ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Trec = Join-Path $Venv "Scripts\trec.exe"
$TeamsTap = Join-Path $ProjectDir "native\teams-tap-win\bin\Release\net8.0\win-x64\publish\teams-tap.exe"
$ToolsDir = Join-Path $ProjectDir "tools"
$WhisperZip = "https://github.com/ggml-org/whisper.cpp/releases/latest/download/whisper-bin-x64.zip"
$MinBuild = 19041
$DaemonTask = "\teams-recorder\daemon"
$script:Step = 0
$script:Warnings = New-Object System.Collections.Generic.List[string]

function Step($text) { $script:Step++; Write-Host ""; Write-Host "[$($script:Step)] $text" -ForegroundColor White }
function Ok($text) { Write-Host "  + $text" -ForegroundColor Green }
function Warn($text) { Write-Host "  ! $text" -ForegroundColor Yellow; $script:Warnings.Add($text) }
function Die($text) { Write-Host "  x $text" -ForegroundColor Red; exit 1 }
function Run([scriptblock]$block, [string]$what) {
    if ($DryRun) { Write-Host "  (dry run) $what"; return }
    $global:LASTEXITCODE = 0          # a stale code from an earlier native call must not fail this step
    try { & $block } catch { Die "$what failed: $_" }
    if ($LASTEXITCODE -ne 0) { Die "$what failed (exit $LASTEXITCODE)" }
}
# Windows PowerShell 5.1 turns a native command's redirected stderr into a terminating error
# when $ErrorActionPreference is Stop; the probes below set it to Continue locally.
function Interactive { return (-not $Yes) -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected }
function Confirm-Step($question, [bool]$default = $true) {
    if (-not (Interactive)) { return $default }
    $hint = if ($default) { "[Y/n]" } else { "[y/N]" }
    $answer = Read-Host "  $question $hint"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer -match '^[Yy]'
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Winget-Install($id) {
    Run { winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements } "winget install $id"
    Refresh-Path
}
function Find-Python {
    $ErrorActionPreference = "Continue"
    foreach ($candidate in @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3.13"), @("python"))) {
        $exe = $candidate[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $extra = @($candidate | Select-Object -Skip 1)
        & $exe @extra -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null
        if ($LASTEXITCODE -eq 0) { return ,$candidate }
    }
    return $null
}
function Settings {
    $map = @{}
    & $VenvPython (Join-Path $ProjectDir "scripts\config_tool.py") get | ForEach-Object {
        $i = $_.IndexOf("="); if ($i -gt 0) { $map[$_.Substring(0, $i)] = $_.Substring($i + 1) }
    }
    return $map
}
function Set-Config($section, $key, $value) {
    Run { & $VenvPython (Join-Path $ProjectDir "scripts\config_tool.py") set $section $key $value } "set [$section] $key"
}
function Find-Whisper {
    $onPath = Get-Command whisper-cli -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    if (Test-Path $ToolsDir) {
        $found = Get-ChildItem -Path $ToolsDir -Recurse -Filter "whisper-cli.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}
function Task-Owner {
    $ErrorActionPreference = "Continue"
    $xml = schtasks /Query /TN $DaemonTask /XML 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $xml) { return $null }
    $doc = [xml]($xml -join "`n")
    return $doc.Task.Actions.Exec.WorkingDirectory
}

Write-Host "teams-recorder installer" -ForegroundColor White
Write-Host $ProjectDir
if ($DryRun) { Write-Host "Dry run: nothing will be changed." -ForegroundColor Yellow }

# -------------------------------------------------------------------------------------------
Step "Windows and project location"
$build = [Environment]::OSVersion.Version.Build
if ($build -lt $MinBuild) { Die "Windows build $build found; Windows 10 version 2004 (build $MinBuild) or later is needed to capture Teams audio." }
Ok "Windows build $build"
if ($env:OneDrive -and $ProjectDir.StartsWith($env:OneDrive, [StringComparison]::OrdinalIgnoreCase)) {
    Warn "the project is inside OneDrive; recordings and models (hundreds of MB) would be synced. Consider C:\Projetos\teams-recorder."
} else { Ok "location is outside OneDrive" }
if (Get-AppxPackage -Name MSTeams -ErrorAction SilentlyContinue) { Ok "Microsoft Teams installed" }
else { Warn "the new Microsoft Teams app was not found; install it before your first call." }

# -------------------------------------------------------------------------------------------
Step "Packages (winget)"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Die "winget is missing. Install 'App Installer' from the Microsoft Store, then run this script again."
}
$python = Find-Python
if ($python) { Ok "Python: $($python -join ' ')" }
else {
    Winget-Install "Python.Python.3.12"
    $python = Find-Python
    if (-not $python -and -not $DryRun) { Die "Python 3.11+ is still not found; open a new terminal and run this script again." }
    Ok "Python 3.12 installed"
}
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) { Ok "ffmpeg" }
else { Winget-Install "Gyan.FFmpeg"; Ok "ffmpeg installed" }

# -------------------------------------------------------------------------------------------
Step "whisper.cpp (transcription)"
$whisper = Find-Whisper
if ($whisper) { Ok "whisper-cli: $whisper" }
else {
    $zip = Join-Path $env:TEMP "whisper-bin-x64.zip"
    Run { Invoke-WebRequest -Uri $WhisperZip -OutFile $zip -UseBasicParsing } "download $WhisperZip"
    Run { Expand-Archive -Force -Path $zip -DestinationPath (Join-Path $ToolsDir "whisper") } "unpack into tools\whisper"
    $whisper = Find-Whisper
    if ($whisper) { Ok "whisper-cli: $whisper" }
    elseif (-not $DryRun) { Warn "whisper-cli.exe was not found in the downloaded archive; see https://github.com/ggml-org/whisper.cpp/releases" }
}

# -------------------------------------------------------------------------------------------
Step "Python environment"
function Test-Venv {
    $ErrorActionPreference = "Continue"
    if (-not (Test-Path $VenvPython)) { return $false }
    & $VenvPython -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null
    return ($LASTEXITCODE -eq 0)
}
$ok = Test-Venv
if ($ok) { Ok "virtualenv exists" }
else {
    $pyExe = $python[0]; $pyArgs = @($python | Select-Object -Skip 1)
    Run { & $pyExe @pyArgs -m venv $Venv } "create .venv"
    Ok "virtualenv created"
}
Run { & $VenvPython -m pip install --quiet --upgrade pip } "upgrade pip"
Run { & $VenvPython -m pip install --quiet -e $ProjectDir } "pip install -e ."
Ok "teams-recorder installed in .venv (command: $Trec)"

# -------------------------------------------------------------------------------------------
Step "Capture program (teams-tap.exe)"
if (Test-Path $TeamsTap) { Ok "teams-tap.exe present" }
else {
    if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { Winget-Install "Microsoft.DotNet.SDK.8" }
    Run { & (Join-Path $ProjectDir "scripts\build-native-windows.ps1") } "build teams-tap.exe"
    Ok "built $TeamsTap"
}

# -------------------------------------------------------------------------------------------
Step "Settings (config.toml)"
if ($DryRun -and -not (Test-Path $VenvPython)) {
    Warn "dry run without a virtualenv: the remaining steps are only listed"
    Write-Host ""; Write-Host "Dry run finished."; exit 0
}
$s = Settings
if (-not $Name -and (Interactive)) {
    $current = if ($s["user_name"]) { $s["user_name"] } else { "none" }
    $Name = Read-Host "  Your name as people say it in meetings [$current]"
}
if (-not $Name) { $Name = $s["user_name"] }
if ($Name -ne $s["user_name"]) { Set-Config "user" "name" $Name }
Ok "user name: $Name"
if (-not $Provider -and (Interactive)) {
    Write-Host "  The analysis can use your Claude subscription (claude-code) or the pay-per-use API (api)."
    $Provider = Read-Host "  LLM provider [$($s["provider"])]"
}
if (-not $Provider) { $Provider = $s["provider"] }
if ($Provider -notin @("claude-code", "api")) { Die "provider must be claude-code or api" }
if ($Provider -ne $s["provider"]) { Set-Config "llm" "provider" $Provider }
Ok "LLM provider: $Provider"
if ($Provider -eq "claude-code") {
    if (Get-Command claude -ErrorAction SilentlyContinue) { Ok "Claude Code found; make sure you are logged in (run 'claude' once and use /login)" }
    else { Warn "Claude Code is not installed. Install it with: irm https://claude.ai/install.ps1 | iex, then run 'claude' and log in." }
} else {
    $envFile = Join-Path $ProjectDir ".env"
    if (-not (Test-Path $envFile)) {
        Run { Copy-Item (Join-Path $ProjectDir ".env.example") $envFile } "create .env"
        Warn "created .env; paste your ANTHROPIC_API_KEY into it (console.anthropic.com)"
    } else { Ok ".env exists" }
}

# -------------------------------------------------------------------------------------------
Step "Transcription model"
$model = $s["model_path"]
if ((Test-Path $model) -and ((Get-Item $model).Length -gt 0)) { Ok "$(Split-Path -Leaf $model) present" }
elseif ($SkipModel) { Warn "model skipped (-SkipModel); download it later with scripts\download-model.ps1" }
else {
    $modelName = [IO.Path]::GetFileNameWithoutExtension($model) -replace '^ggml-', ''
    Write-Host "  downloading $modelName (several hundred MB)"
    Run { & (Join-Path $ProjectDir "scripts\download-model.ps1") -Name $modelName -Dir (Split-Path -Parent $model) } "download model"
    Ok "model saved to $model"
}
$vad = $s["vad_path"]
if ($vad -and -not (Test-Path $vad) -and -not $SkipModel) {
    $vadName = [IO.Path]::GetFileNameWithoutExtension($vad) -replace '^ggml-', ''
    Run { & (Join-Path $ProjectDir "scripts\download-model.ps1") -Name $vadName -Dir (Split-Path -Parent $vad) } "download VAD model"
}

# -------------------------------------------------------------------------------------------
Step "Checking the installation (trec doctor)"
if ($DryRun) { Write-Host "  (dry run) $Trec doctor" }
else {
    & $Trec doctor | ForEach-Object { Write-Host "  $_" }
    if ($LASTEXITCODE -eq 0) { Ok "all checks passed" } else { Warn "trec doctor reported a problem above; fix it and run 'trec doctor' again" }
}

# -------------------------------------------------------------------------------------------
Step "Background tasks (Task Scheduler)"
if ($NoAgent) { Warn "skipped (-NoAgent); install later with: $Trec agent install" }
else {
    $owner = Task-Owner
    if ($owner -and ($owner.TrimEnd('\') -ne $ProjectDir.TrimEnd('\')) -and -not (Confirm-Step "The tasks currently run the copy at $owner. Point them to this one instead?" $false)) {
        Warn "tasks left pointing to $owner"
    } elseif (Test-Path $s["active"]) {
        Warn "a recording is in progress; tasks not reinstalled. Run '$Trec agent install' after the call."
    } elseif (Confirm-Step "Install the recorder (starts at logon) and the 6 pm planner?" $true) {
        Run { & $Trec agent install | ForEach-Object { Write-Host "  $_" } } "trec agent install"
        Ok "daemon and planner installed"
    } else { Warn "tasks not installed; run '$Trec agent install' when ready" }
}

# -------------------------------------------------------------------------------------------
Step "Microphone access"
Write-Host "  Windows must let desktop apps use the microphone, or the microphone track comes out silent:"
Write-Host "    Settings > Privacy & security > Microphone > Let desktop apps access your microphone (On)."
Write-Host "  Teams audio itself needs no permission."
if (-not $DryRun -and (Interactive) -and (Confirm-Step "Open that settings page now?" $false)) { Start-Process "ms-settings:privacy-microphone" }

# -------------------------------------------------------------------------------------------
Write-Host ""
if ($DryRun) { Write-Host "Dry run finished; nothing was changed." -ForegroundColor White; exit 0 }
if ($script:Warnings.Count -eq 0) { Write-Host "Done. Everything is installed." -ForegroundColor White }
else {
    Write-Host "Done. Installed, with $($script:Warnings.Count) item(s) to check:" -ForegroundColor White
    foreach ($w in $script:Warnings) { Write-Host "  ! $w" -ForegroundColor Yellow }
}
Write-Host ""
Write-Host "Next: join a Teams call; recording starts by itself. Useful commands:"
Write-Host "  $Trec status          meetings and their state"
Write-Host "  $Trec agent status    is the recorder running?"
Write-Host "  Get-Content -Wait `"$($s["data_dir"])\log\teams-recorder.log`""
