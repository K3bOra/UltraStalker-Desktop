param(
    [string]$InstallDir = "$(Join-Path $env:LOCALAPPDATA 'Programs\Ultra Stalker Desktop')"
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Fail([string]$Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    exit 1
}

function Pass([string]$Message) {
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

try {
    $InstallDir = [System.IO.Path]::GetFullPath($InstallDir)
    $Exe = Join-Path $InstallDir 'UltraStalkerDesktop.exe'
    $Mpv = Join-Path $InstallDir 'mpv.exe'
    $BuildSelfTest = Join-Path $InstallDir 'SELF_TEST.json'
    $ProvenancePath = Join-Path $InstallDir 'provenance.json'
    $ReleaseHashesPath = Join-Path $InstallDir 'RELEASE_SHA256.json'
    $RuntimeSelfTest = Join-Path $env:LOCALAPPDATA 'UltraStalker\diagnostics\SELF_TEST.json'

    foreach ($Path in @($Exe, $Mpv, $BuildSelfTest, $ProvenancePath, $ReleaseHashesPath)) {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            Fail "Required installed file is missing: $([System.IO.Path]::GetFileName($Path))"
        }
    }
    Pass 'Required installed runtime files are present'

    $BuildReport = Get-Content -LiteralPath $BuildSelfTest -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($BuildReport.report_kind -ne 'build' -or -not $BuildReport.passed) {
        Fail 'Installed SELF_TEST.json is not the passed immutable build self-test report'
    }
    Pass 'Immutable build self-test report is valid'

    $Provenance = Get-Content -LiteralPath $ProvenancePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Provenance.product -ne 'Ultra Stalker Desktop' -or $Provenance.developer -ne 'Ahmed L-HadarY') {
        Fail 'Installed provenance identity does not match Ultra Stalker Desktop / Ahmed L-HadarY'
    }
    if ($Provenance.platform -ne 'windows-x64') {
        Fail "Unexpected installed platform: $($Provenance.platform)"
    }

    $ReleaseHashes = Get-Content -LiteralPath $ReleaseHashesPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $ExeHash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
    $MpvHash = (Get-FileHash -LiteralPath $Mpv -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ExeHash -ne ([string]$ReleaseHashes.'UltraStalkerDesktop.exe').ToLowerInvariant()) {
        Fail 'Installed application executable SHA256 does not match RELEASE_SHA256.json'
    }
    if ($MpvHash -ne ([string]$ReleaseHashes.'mpv.exe').ToLowerInvariant()) {
        Fail 'Installed mpv SHA256 does not match RELEASE_SHA256.json'
    }
    Pass 'Installed executable and mpv hashes match the release payload'

    $BuildHashBefore = (Get-FileHash -LiteralPath $BuildSelfTest -Algorithm SHA256).Hash.ToLowerInvariant()
    $RuntimeStampBefore = if (Test-Path -LiteralPath $RuntimeSelfTest) {
        (Get-Item -LiteralPath $RuntimeSelfTest).LastWriteTimeUtc
    } else {
        [DateTime]::MinValue
    }

    $SelfTestProcess = Start-Process -FilePath $Exe -ArgumentList '--self-test' -WorkingDirectory $InstallDir -Wait -PassThru
    if ($null -eq $SelfTestProcess) {
        Fail 'Installed runtime self-test process did not start'
    }
    $ExitCode = [int]$SelfTestProcess.ExitCode
    if ($ExitCode -ne 0) {
        Fail "Installed runtime self-test exited with code $ExitCode"
    }

    if (-not (Test-Path -LiteralPath $RuntimeSelfTest -PathType Leaf)) {
        Fail 'Installed runtime self-test did not create the AppData diagnostic report'
    }
    $RuntimeItem = Get-Item -LiteralPath $RuntimeSelfTest
    if ($RuntimeItem.LastWriteTimeUtc -le $RuntimeStampBefore) {
        Fail 'Installed runtime self-test report was not refreshed'
    }

    $BuildHashAfter = (Get-FileHash -LiteralPath $BuildSelfTest -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($BuildHashAfter -ne $BuildHashBefore) {
        Fail 'Installed --self-test modified the fingerprinted build SELF_TEST.json'
    }
    Pass 'Installed --self-test leaves the fingerprinted build report unchanged'

    $RuntimeReport = Get-Content -LiteralPath $RuntimeSelfTest -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($RuntimeReport.report_kind -ne 'runtime' -or -not $RuntimeReport.passed) {
        Fail 'Runtime self-test report is missing, failed, or has the wrong report kind'
    }
    if ($RuntimeReport.checks.runtime_platform -ne 'win32' -or [int]$RuntimeReport.checks.python_bits -ne 64) {
        Fail 'Installed runtime self-test did not execute as Windows x64'
    }
    if (-not $RuntimeReport.checks.sqlite -or -not $RuntimeReport.checks.database_integrity -or -not $RuntimeReport.checks.mpv -or -not $RuntimeReport.checks.credential_manager -or -not $RuntimeReport.checks.credential_cleanup -or -not $RuntimeReport.checks.qt_runtime) {
        Fail 'One or more installed runtime checks failed'
    }
    if ($RuntimeReport.checks.database_integrity_status -notin @('ok', 'not_created')) {
        Fail ('Installed user database integrity check failed: ' + $RuntimeReport.checks.database_integrity_status)
    }
    if ($RuntimeReport.checks.qt_platform -ne 'windows') {
        Fail "Installed Qt platform is not the Windows plugin: $($RuntimeReport.checks.qt_platform)"
    }
    if (-not $RuntimeReport.checks.release_integrity -or $RuntimeReport.release_integrity.status -ne 'ok') {
        Fail 'Installed runtime release-integrity verification did not pass'
    }
    if ($RuntimeReport.release_integrity.build_id -ne $Provenance.build_id) {
        Fail 'Installed runtime release-integrity Build ID does not match provenance'
    }
    if (([string]$RuntimeReport.artifacts.application_sha256).ToLowerInvariant() -ne $ExeHash) {
        Fail 'Runtime self-test application hash does not bind to the installed executable'
    }
    if (([string]$RuntimeReport.artifacts.mpv_sha256).ToLowerInvariant() -ne $MpvHash) {
        Fail 'Runtime self-test mpv hash does not bind to the installed player'
    }
    Pass 'Installed Windows x64 runtime self-test passed and is bound to the installed artifacts'

    $InstallRoot = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\') + '\'
    $RuntimePath = [System.IO.Path]::GetFullPath($RuntimeSelfTest)
    if ($RuntimePath.StartsWith($InstallRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        Fail 'Runtime self-test report was written inside the fingerprinted install payload'
    }
    Pass 'Runtime self-test report is isolated under LocalAppData diagnostics'

    Write-Host "[OK] Ultra Stalker Desktop installed runtime verification passed." -ForegroundColor Cyan
    exit 0
}
catch {
    Fail $_.Exception.Message
}
