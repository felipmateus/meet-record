# Downloads a whisper.cpp ggml model from Hugging Face (Windows counterpart of download-model.sh).
# Usage: scripts\download-model.ps1 [-Name large-v3-turbo-q5_0] [-Dir <project>\data\models]
param(
    [string]$Name = "large-v3-turbo-q5_0",
    [string]$Dir = (Join-Path (Split-Path -Parent $PSScriptRoot) "data\models")
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # the progress bar makes Invoke-WebRequest very slow on PowerShell 5.1
$file = "ggml-$Name.bin"
if ($Name -like "silero-*") { $url = "https://huggingface.co/ggml-org/whisper-vad/resolve/main/$file" }
else { $url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$file" }
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$target = Join-Path $Dir $file
if ((Test-Path $target) -and ((Get-Item $target).Length -gt 0)) { Write-Host "already exists: $target"; exit 0 }
Write-Host "downloading $url"
Invoke-WebRequest -Uri $url -OutFile "$target.part" -UseBasicParsing
Move-Item -Force "$target.part" $target
Write-Host ("model saved to {0} ({1:N0} MB)" -f $target, ((Get-Item $target).Length / 1MB))
