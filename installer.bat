@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows.ps1" -Mode install %*
set "STUDIO_EXIT=%ERRORLEVEL%"
pause
exit /b %STUDIO_EXIT%
