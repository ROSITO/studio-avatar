@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows.ps1" -Mode launch %*
set "STUDIO_EXIT=%ERRORLEVEL%"
if not "%STUDIO_EXIT%"=="0" pause
exit /b %STUDIO_EXIT%
