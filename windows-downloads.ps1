# Direct downloads with pinned SHA-256 checks. No WinGet, Store or Python required.
function Get-VerifiedDownload($Package, [string]$Cache) {
    New-Item -ItemType Directory -Path $Cache -Force | Out-Null
    $destination = Join-Path $Cache $Package.file
    if (Test-Path -LiteralPath $destination) {
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -eq $Package.sha256) {
            return $destination
        }
        Remove-Item -LiteralPath $destination -Force
    }
    if (-not $Package.url.StartsWith('https://')) { throw 'Le telechargement exige une URL HTTPS.' }
    $temporary = "$destination.$([Guid]::NewGuid().ToString('N')).part"
    try {
        Write-Host "Telechargement : $($Package.file)"
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $previousProgress = $ProgressPreference
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $Package.url -OutFile $temporary -UseBasicParsing
        } finally { $ProgressPreference = $previousProgress }
        if ((Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash -ne $Package.sha256) {
            throw "Empreinte SHA-256 incorrecte pour $($Package.file). Le fichier ne sera pas execute."
        }
        Move-Item -LiteralPath $temporary -Destination $destination -Force
        return $destination
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Invoke-PrerequisiteInstaller([string]$Executable, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) {
        throw "Installation de $([IO.Path]::GetFileName($Executable)) interrompue (code $($process.ExitCode))."
    }
    if ($process.ExitCode -eq 3010) { Write-Host 'Le prerequis signale un redemarrage Windows necessaire.' }
}

function Install-PortableFFmpeg($Package, [string]$Cache, [string]$Tools) {
    $folder = Join-Path $Tools $Package.directory
    $bin = Join-Path $folder 'bin'
    if ((Test-Path (Join-Path $bin 'ffmpeg.exe')) -and (Test-Path (Join-Path $bin 'ffprobe.exe'))) { return $bin }
    $archive = Get-VerifiedDownload $Package $Cache
    New-Item -ItemType Directory -Path $Tools -Force | Out-Null
    $temporary = Join-Path $Tools ('.extract-' + [Guid]::NewGuid().ToString('N'))
    try {
        Expand-Archive -LiteralPath $archive -DestinationPath $temporary
        $unpacked = Join-Path $temporary $Package.directory
        foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
            if (-not (Test-Path (Join-Path $unpacked "bin\$name"))) { throw "Archive FFmpeg incomplete : $name absent." }
        }
        if (Test-Path -LiteralPath $folder) { Remove-Item -LiteralPath $folder -Recurse -Force }
        Move-Item -LiteralPath $unpacked -Destination $folder
        return $bin
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
    }
}
