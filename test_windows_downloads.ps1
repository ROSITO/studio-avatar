# Tests use local fixture bytes; no downloads or installers are executed.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows-downloads.ps1')
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('studio-download-tests-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
$script:payload = [Text.Encoding]::UTF8.GetBytes('verified local fixture')
$script:downloadCount = 0
function Invoke-WebRequest($Uri, $OutFile, [switch]$UseBasicParsing) {
    $script:downloadCount++
    [IO.File]::WriteAllBytes($OutFile, $script:payload)
}
function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Assert-Throws([scriptblock]$Action) {
    $failed = $false
    try { & $Action | Out-Null } catch { $failed = $true }
    Assert-True $failed 'Expected the operation to fail'
}
try {
    $fixture = Join-Path $temporary 'fixture'
    [IO.File]::WriteAllBytes($fixture, $script:payload)
    $package = [PSCustomObject]@{file='test.exe'; url='https://example.invalid/test'; sha256=(Get-FileHash $fixture -Algorithm SHA256).Hash}
    $cache = Join-Path $temporary 'cache'
    $download = Get-VerifiedDownload $package $cache
    Assert-True ($script:downloadCount -eq 1) 'Missing download was not fetched'
    Get-VerifiedDownload $package $cache | Out-Null
    Assert-True ($script:downloadCount -eq 1) 'Valid cached download was unnecessarily fetched again'
    Set-Content -LiteralPath $download -Value 'corrupted'
    Get-VerifiedDownload $package $cache | Out-Null
    Assert-True ($script:downloadCount -eq 2) 'Corrupted cache was not replaced'
    $package.file = 'wrong-hash.exe'; $package.sha256 = '0' * 64
    Assert-Throws { Get-VerifiedDownload $package $cache }
    Assert-True (-not (Test-Path (Join-Path $cache $package.file))) 'Invalid file was accepted'
    Assert-True (@(Get-ChildItem $cache -Filter '*.part').Count -eq 0) 'Partial download was not cleaned up'
    $package.url = 'http://example.invalid/insecure'
    $count = $script:downloadCount
    Assert-Throws { Get-VerifiedDownload $package $cache }
    Assert-True ($script:downloadCount -eq $count) 'Insecure URL was downloaded'

    # Validate extraction and repair using a real ZIP with fixture files.
    function Test-StudioFFmpeg([string]$Bin) {
        foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
            $file = Join-Path $Bin $name
            if (-not (Test-Path -LiteralPath $file) -or (Get-Content -LiteralPath $file) -ne 'fixture') { return $false }
        }
        return $true
    }
    $source = Join-Path $temporary 'ffmpeg-test'
    New-Item -ItemType Directory -Path (Join-Path $source 'bin') | Out-Null
    foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) { Set-Content (Join-Path $source "bin\$name") 'fixture' }
    $zip = Join-Path $temporary 'fixture.zip'
    Compress-Archive -LiteralPath $source -DestinationPath $zip
    $script:payload = [IO.File]::ReadAllBytes($zip)
    $package = [PSCustomObject]@{file='ffmpeg.zip'; directory='ffmpeg-test'; url='https://example.invalid/ffmpeg'; sha256=(Get-FileHash $zip -Algorithm SHA256).Hash}
    $bin = Install-PortableFFmpeg $package $cache (Join-Path $temporary 'tools')
    Assert-True (Test-Path (Join-Path $bin 'ffprobe.exe')) 'FFprobe missing after extraction'
    $count = $script:downloadCount
    Install-PortableFFmpeg $package $cache (Join-Path $temporary 'tools') | Out-Null
    Assert-True ($count -eq $script:downloadCount) 'Complete FFmpeg was installed twice'
    Set-Content -LiteralPath (Join-Path $bin 'ffmpeg.exe') 'corrupted'
    Install-PortableFFmpeg $package $cache (Join-Path $temporary 'tools') | Out-Null
    Assert-True (Test-StudioFFmpeg $bin) 'Corrupted FFmpeg tools were not restored'
    Assert-True ($count -eq $script:downloadCount) 'Verified ZIP was not reused for repair'

    $script:installerCode = 1603
    function Start-Process($FilePath, $ArgumentList, [switch]$Wait, [switch]$PassThru) {
        return [PSCustomObject]@{ExitCode=$script:installerCode}
    }
    Assert-Throws { Invoke-PrerequisiteInstaller 'fixture.exe' @('/quiet') }
    $script:installerCode = 3010
    Invoke-PrerequisiteInstaller 'fixture.exe' @('/quiet')
    Write-Host 'Direct-download tests OK: hashes, cache, HTTPS, ZIP extraction, installer errors.'
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
