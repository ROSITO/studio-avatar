# Bootstrap prerequisites before invoking Python. Compatible with Windows PowerShell 5.1.
param(
    [ValidateSet('install', 'launch')][string]$Mode = 'install',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$StudioArgs
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
# Discovery must never trigger an install via either Python launcher.
$env:PYTHON_MANAGER_AUTOMATIC_INSTALL = 'false'
$env:PYLAUNCHER_ALLOW_INSTALL = $null
$env:PYLAUNCHER_ALWAYS_INSTALL = $null
$packages = Get-Content -LiteralPath (Join-Path $root 'windows-dependencies.json') -Raw | ConvertFrom-Json
$studioHome = Join-Path $env:LOCALAPPDATA 'StudioAvatar'
$cache = Join-Path $studioHome 'downloads'
$tools = Join-Path $studioHome 'tools'
$localFFmpeg = Join-Path (Join-Path $tools $packages.ffmpeg.directory) 'bin'
$sessionPath = $env:Path
. (Join-Path $root 'windows-downloads.ps1')

function Update-SessionPath {
    # Keep custom paths from this console and add changes made by installers.
    $env:Path = "$sessionPath;" + [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
        [Environment]::GetEnvironmentVariable('Path', 'User') + ";$env:LOCALAPPDATA\Microsoft\WinGet\Links"
}

function Test-StudioPython([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        & $Executable -c "import ensurepip, sys, sysconfig, venv; sys.exit(0 if sys.version_info[:2] in ((3,12),(3,13)) and sysconfig.get_platform() == 'win-amd64' and not sysconfig.get_config_var('Py_GIL_DISABLED') else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-StudioPython {
    $candidates = @()
    $saved = Join-Path $root '.studio-python.txt'
    if (Test-Path -LiteralPath $saved -PathType Leaf) {
        $candidates += ([string](Get-Content -LiteralPath $saved -Raw -ErrorAction SilentlyContinue)).Trim()
    }
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
            $registration = Get-Item -LiteralPath $key -ErrorAction SilentlyContinue
            if ($registration) {
                $candidates += $registration.GetValue('ExecutablePath')
                $installPath = $registration.GetValue('')
                if ($installPath) { $candidates += Join-Path $installPath 'python.exe' }
            }
        }
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike '*\WindowsApps\*') { $candidates += $command.Source }
    foreach ($candidate in $candidates) {
        if (Test-StudioPython $candidate) { return $candidate }
    }
    return $null
}

function Test-StudioVCRuntime([version]$MinimumVersion) {
    $registry = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', 'Registry64')
    try {
        $runtime = $registry.OpenSubKey('SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64')
        if (-not $runtime) { return $false }
        try {
            $version = $null
            $installed = ([string]$runtime.GetValue('Version')).TrimStart('v')
            return $runtime.GetValue('Installed') -eq 1 -and
                [version]::TryParse($installed, [ref]$version) -and $version -ge $MinimumVersion
        } finally { $runtime.Dispose() }
    } finally { $registry.Dispose() }
}

try {
    Update-SessionPath
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') {
        throw 'Cette installation Windows necessite un processeur x64. Aucun moteur ne sera installe sur cette architecture.'
    }
    $python = Find-StudioPython
    if ($Mode -eq 'install' -and $StudioArgs -contains '--plan') {
        Write-Host 'Prerequis automatiques : Python 3.13 x64 si absent, FFmpeg/FFprobe, runtime Microsoft Visual C++ x64.'
        if ($python) { & $python (Join-Path $root 'installer.py') @StudioArgs; exit $LASTEXITCODE }
        Write-Host 'Python compatible absent. Relancez sans --plan pour installer les prerequis et detecter le moteur.'
        exit 0
    }
    if ($Mode -eq 'install' -and -not $python) {
        $executable = Get-VerifiedDownload $packages.python $cache
        Invoke-PrerequisiteInstaller $executable @('/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1', 'InstallLauncherAllUsers=0', 'Include_test=0')
        Update-SessionPath
        $python = Find-StudioPython
        if (-not $python) { throw "Python 3.13 x64 reste introuvable apres installation. Consultez les erreurs ci-dessus." }
    }
    if (-not $python) { throw 'Installation requise : lancez installer.bat une premiere fois.' }
    if (Test-StudioFFmpeg $localFFmpeg) {
        $env:Path = "$localFFmpeg;$env:Path"
    } elseif (-not (Test-StudioFFmpeg)) {
        if ($Mode -eq 'launch') { throw 'FFmpeg/FFprobe indisponibles : relancez installer.bat.' }
        $bin = Install-PortableFFmpeg $packages.ffmpeg $cache $tools
        $env:Path = "$bin;$env:Path"
    }
    if ($Mode -eq 'install') {
        if (-not (Test-StudioVCRuntime $packages.vcredist.version)) {
            $executable = Get-VerifiedDownload $packages.vcredist $cache
            Invoke-PrerequisiteInstaller $executable @('/install', '/passive', '/norestart')
            if (-not (Test-StudioVCRuntime $packages.vcredist.version)) {
                throw 'Le runtime Visual C++ x64 est requis. Une autorisation Windows peut etre necessaire; relancez installer.bat apres installation.'
            }
        }
        # Remember only a local executable path; this file is never published.
        Set-Content -LiteralPath (Join-Path $root '.studio-python.txt') -Value $python -Encoding UTF8
        & $python (Join-Path $root 'installer.py') @StudioArgs
        exit $LASTEXITCODE
    }
    & $python (Join-Path $root 'lancer.py') @StudioArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "ERREUR : $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
