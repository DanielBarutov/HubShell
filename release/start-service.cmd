@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-service.ps1"
if errorlevel 1 (
  echo Service setup failed. Run as administrator and check server.ini.
  pause
  exit /b 1
)
pause
