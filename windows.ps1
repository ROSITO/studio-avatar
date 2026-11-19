# Bootstrap prerequisites before invoking Python. Compatible with Windows PowerShell 5.1.
param(
    [ValidateSet('install', 'launch')][string]$Mode = 'install',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$StudioArgs
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Update-SessionPath {
    # Keep custom paths from this console and add changes made by installers.
    $env:Path = "$env:Path;" + [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
        [Environment]::GetEnvironmentVariable('Path', 'User') + ";$env:LOCALAPPDATA\Microsoft\WinGet\Links"
}

function Test-StudioPython([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        & $Executable -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3,12),(3,13)) and sys.maxsize > 2**32 else 1)' 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-StudioPython {
    $candidates = @()
    $saved = Join-Path $root '.studio-python.txt'
    if (Test-Path -LiteralPath $saved) { $candidates += (Get-Content -LiteralPath $saved -Raw).Trim() }
    foreach ($version in @('3.13', '3.12')) {
        if (Get-Command py.exe -ErrorAction SilentlyContinue) {
            try {
                $found = & py.exe "-$version" -c 'import sys; print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0) { $candidates += $found }
            } catch { }
        }
        $compact = $version.Replace('.', '')
        $candidates += "$env:LOCALAPPDATA\Programs\Python\Python$compact\python.exe"
        foreach ($hive in @('HKCU:', 'HKLM:')) {
            $key = "$hive\Software\Python\PythonCore\$version\InstallPath"
            if (Test-Path $key) { $candidates += Join-Path ((Get-Item $key).GetValue('')) 'python.exe' }
        }
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike '*\WindowsApps\*') { $candidates += $command.Source }
    foreach ($candidate in $candidates) {
        if (Test-StudioPython $candidate) { return $candidate }
    }
    return $null
}

function Install-Package([string]$Id, [switch]$UserScope) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'WinGet est absent. Installez/actualisez App Installer depuis https://apps.microsoft.com/detail/9nblggh4nns1 puis relancez installer.bat.'
    }
    Write-Host "Installation du prerequis : $Id"
    $arguments = @('install', '--id', $Id, '--exact', '--source', 'winget', '--architecture', 'x64',
        '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity', '--silent')
    if ($UserScope) { $arguments += @('--scope', 'user') }
    & winget.exe @arguments
    # WinGet also returns a nonzero code when the latest version is already installed.
    # Callers always verify the prerequisite afterwards rather than trusting this code.
    Update-SessionPath
}

try {
    Update-SessionPath
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') {
        throw 'Cette installation Windows necessite un processeur x64. Aucun moteur ne sera installe sur cette architecture.'
    }
    $python = Find-StudioPython
    if ($Mode -eq 'install') {
        if ($StudioArgs -contains '--plan') {
            Write-Host 'Prerequis automatiques : Python 3.13 x64 si absent, FFmpeg/FFprobe, runtime Microsoft Visual C++ x64.'
            if ($python) { & $python (Join-Path $root 'installer.py') @StudioArgs; exit $LASTEXITCODE }
            Write-Host 'Python compatible absent. Relancez sans --plan pour installer les prerequis et detecter le moteur.'
            exit 0
        }
        if (-not $python) {
            Install-Package 'Python.Python.3.13' -UserScope
            $python = Find-StudioPython
            if (-not $python) { throw 'Python 3.13 x64 reste introuvable apres installation. Consultez la sortie WinGet ci-dessus.' }
        }
        if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
            Install-Package 'Gyan.FFmpeg' -UserScope
        }
        if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
            throw 'FFmpeg/FFprobe introuvables apres installation. Consultez la sortie WinGet ci-dessus.'
        }
        & ffmpeg.exe -version >$null
        if ($LASTEXITCODE -ne 0) { throw 'FFmpeg est present mais ne demarre pas.' }
        & ffprobe.exe -version >$null
        if ($LASTEXITCODE -ne 0) { throw 'FFprobe est present mais ne demarre pas.' }
        $vcKey = 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
        $vc = Get-ItemProperty -Path $vcKey -ErrorAction SilentlyContinue
        if (-not $vc -or $vc.Installed -ne 1) { Install-Package 'Microsoft.VCRedist.2015+.x64' }
        $vc = Get-ItemProperty -Path $vcKey -ErrorAction SilentlyContinue
        if (-not $vc -or $vc.Installed -ne 1) {
            throw 'Le runtime Visual C++ x64 est requis. Une autorisation Windows peut etre necessaire; relancez installer.bat apres installation.'
        }
        # Remember only a local executable path; this file is never published.
        Set-Content -LiteralPath (Join-Path $root '.studio-python.txt') -Value $python -Encoding UTF8
        & $python (Join-Path $root 'installer.py') @StudioArgs
        exit $LASTEXITCODE
    }
    if (-not $python) { throw 'Installation requise : lancez installer.bat une premiere fois.' }
    & $python (Join-Path $root 'lancer.py') @StudioArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "ERREUR : $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
