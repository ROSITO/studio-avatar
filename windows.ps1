# Bootstrap prerequisites before invoking Python. Compatible with Windows PowerShell 5.1.
param(
    [ValidateSet('install', 'launch')][string]$Mode = 'install',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$StudioArgs
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$packages = Get-Content -LiteralPath (Join-Path $root 'windows-dependencies.json') -Raw | ConvertFrom-Json
$studioHome = Join-Path $env:LOCALAPPDATA 'StudioAvatar'
$cache = Join-Path $studioHome 'downloads'
$tools = Join-Path $studioHome 'tools'
. (Join-Path $root 'windows-downloads.ps1')

function Update-SessionPath {
    # Keep custom paths from this console and add changes made by installers.
    $env:Path = "$env:Path;" + [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
        [Environment]::GetEnvironmentVariable('Path', 'User') + ";$env:LOCALAPPDATA\Microsoft\WinGet\Links;" + (Join-Path $tools ($packages.ffmpeg.directory + '\bin'))
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
            $executable = Get-VerifiedDownload $packages.python $cache
            Invoke-PrerequisiteInstaller $executable @('/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1', 'InstallLauncherAllUsers=0', 'Include_test=0')
            Update-SessionPath
            $python = Find-StudioPython
            if (-not $python) { throw "Python 3.13 x64 reste introuvable apres installation. Consultez les erreurs ci-dessus." }
        }
        if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
            $bin = Install-PortableFFmpeg $packages.ffmpeg $cache $tools
            $env:Path = "$bin;$env:Path"
        }
        if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
            throw "FFmpeg/FFprobe introuvables apres installation. Consultez les erreurs ci-dessus."
        }
        & ffmpeg.exe -version >$null
        if ($LASTEXITCODE -ne 0) { throw 'FFmpeg est present mais ne demarre pas.' }
        & ffprobe.exe -version >$null
        if ($LASTEXITCODE -ne 0) { throw 'FFprobe est present mais ne demarre pas.' }
        $vcKey = 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
        $vc = Get-ItemProperty -Path $vcKey -ErrorAction SilentlyContinue
        if (-not $vc -or $vc.Installed -ne 1) {
            $executable = Get-VerifiedDownload $packages.vcredist $cache
            Invoke-PrerequisiteInstaller $executable @('/install', '/passive', '/norestart')
        }
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
