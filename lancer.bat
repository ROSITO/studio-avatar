@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 (
    py -3 lancer.py %*
    goto :done
)
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 (
    python lancer.py %*
    goto :done
)
echo Python 3.10 ou plus recent est requis. Installez Python puis relancez ce fichier.
pause
exit /b 1
:done
set "STUDIO_EXIT=%ERRORLEVEL%"
if not "%STUDIO_EXIT%"=="0" pause
exit /b %STUDIO_EXIT%
