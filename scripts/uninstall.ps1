# Removes what scripts\install.ps1 set up for this copy of teams-recorder.
#
#   scripts\uninstall.ps1 [-All] [-Yes]
#
# Always: ends and deletes the scheduled tasks (daemon and planner), but only when they run this
# copy of the project. With -All: also deletes .venv and the teams-tap.exe build. Never deletes
# your recordings, transcripts, plans or models (the data folder), nor winget packages.
param([switch]$All, [switch]$Yes)
$ProjectDir = Split-Path -Parent $PSScriptRoot
$Trec = Join-Path $ProjectDir ".venv\Scripts\trec.exe"
$dataDir = Join-Path $ProjectDir "data"
if (Test-Path $Trec) {
    $line = & $Trec status 2>$null | Where-Object { $_ -like "Data dir: *" } | Select-Object -First 1
    if ($line) { $dataDir = $line.Substring(10) }
}
foreach ($name in @("daemon", "planner")) {
    $task = "\teams-recorder\$name"
    $xml = schtasks /Query /TN $task /XML 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Host "${name}: not installed"; continue }
    $owner = ([xml]($xml -join "`n")).Task.Actions.Exec.WorkingDirectory
    if ($owner.TrimEnd('\') -ne $ProjectDir.TrimEnd('\')) { Write-Host "${name}: runs another copy ($owner); left alone"; continue }
    schtasks /End /TN $task 2>$null | Out-Null
    schtasks /Delete /TN $task /F | Out-Null
    Write-Host "${name}: removed"
}
if ($All) {
    $go = $Yes
    if (-not $go) { $go = (Read-Host "Delete .venv and the teams-tap.exe build in $ProjectDir? [y/N]") -match '^[Yy]' }
    if ($go) {
        foreach ($p in @(".venv", "native\teams-tap-win\bin", "native\teams-tap-win\obj")) {
            $full = Join-Path $ProjectDir $p
            if (Test-Path $full) { Remove-Item -Recurse -Force $full }
        }
        Write-Host "removed .venv and the teams-tap.exe build"
    }
}
Write-Host "Your data was kept: $dataDir"
Write-Host "Microphone access for desktop apps can be changed in Settings > Privacy & security > Microphone."
