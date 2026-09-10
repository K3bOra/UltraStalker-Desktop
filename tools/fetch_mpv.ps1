$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Version = '0.41.0'
$Url = 'https://github.com/mpv-player/mpv/releases/download/v0.41.0/mpv-v0.41.0-x86_64-pc-windows-msvc.zip'
$ExpectedSha256 = '4e197f729f5071c6772f35fffd96e0f36e3e8a044bd9479b136bb09b7c6a80ff'
$Root = Split-Path -Parent $PSScriptRoot
$Vendor = Join-Path $Root 'vendor\mpv'
$Temp = Join-Path $env:TEMP ('ultrastalker-mpv-' + [guid]::NewGuid().ToString('N'))
$Zip = Join-Path $Temp 'mpv.zip'
$Extracted = Join-Path $Temp 'extract'

# GitHub requires modern TLS. Windows PowerShell 5.1 on older hosts can still
# inherit a legacy protocol default, so opt into TLS 1.2 explicitly.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

try {
    New-Item -ItemType Directory -Force -Path $Temp, $Extracted | Out-Null
    Write-Host "[INFO] Downloading mpv $Version Windows x64 MSVC..."
    Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing

    $Actual = (Get-FileHash -Algorithm SHA256 -Path $Zip).Hash.ToLowerInvariant()
    if ($Actual -ne $ExpectedSha256) {
        throw "mpv SHA256 mismatch. Expected $ExpectedSha256 but got $Actual"
    }
    Write-Host '[OK] mpv archive SHA256 verified.'

    Expand-Archive -Path $Zip -DestinationPath $Extracted -Force
    $Exe = Get-ChildItem -Path $Extracted -Filter 'mpv.exe' -File -Recurse | Select-Object -First 1
    if (-not $Exe) {
        throw 'mpv.exe was not found in the verified archive.'
    }
    $ExeSha256 = (Get-FileHash -Algorithm SHA256 -Path $Exe.FullName).Hash.ToLowerInvariant()

    # Runtime packaging deliberately keeps only the standalone executable.
    # PDB/registration helper files from the upstream archive are not needed by
    # Ultra Stalker Desktop and would substantially inflate the installer.
    if (Test-Path $Vendor) { Remove-Item -Recurse -Force $Vendor }
    New-Item -ItemType Directory -Force -Path $Vendor | Out-Null
    Copy-Item -Path $Exe.FullName -Destination (Join-Path $Vendor 'mpv.exe') -Force

    $Meta = [ordered]@{
        product = 'mpv'
        version = $Version
        source = $Url
        archive_sha256 = $ExpectedSha256
        executable_sha256 = $ExeSha256
        architecture = 'x86_64'
        toolchain = 'MSVC'
        packaged_files = @('mpv.exe')
    } | ConvertTo-Json -Depth 3
    Set-Content -Path (Join-Path $Vendor 'ULTRASTALKER_MPV_PROVENANCE.json') -Value $Meta -Encoding UTF8
    Write-Host "[OK] mpv runtime prepared under $Vendor"
}
finally {
    if (Test-Path $Temp) { Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue }
}
