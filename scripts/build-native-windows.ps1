# Builds teams-tap.exe on Windows. Needs the .NET 8 SDK (winget install Microsoft.DotNet.SDK.8).
$ErrorActionPreference = "Stop"
Push-Location (Join-Path $PSScriptRoot "..\native\teams-tap-win")
try {
    $env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"
    dotnet publish -c Release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "binary: $(Get-Location)\bin\Release\net8.0\win-x64\publish\teams-tap.exe"
} finally { Pop-Location }
