@echo off
rem Double-click to install teams-recorder on Windows (runs scripts\install.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
echo.
pause
