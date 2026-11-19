@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
for %%V in (3.12 3.13 3) do (
    py -%%V -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        py -%%V installer.py %*
        goto :done
    )
)
python installer.py %*
:done
set "STUDIO_EXIT=%ERRORLEVEL%"
pause
exit /b %STUDIO_EXIT%
