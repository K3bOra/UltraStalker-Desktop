param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$SourceDist,
    [string]$OutputPath = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Fail([string]$Message) {
    throw $Message
}

function Invoke-WaitedNativeProcess([string]$FilePath, [string[]]$ArgumentList) {
    $Process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -Wait -PassThru
    if ($null -eq $Process) { Fail 'Native process did not start.' }
    return [int]$Process.ExitCode
}

function File-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-Json([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "Required JSON file is missing: $([System.IO.Path]::GetFileName($Path))"
    }
    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Registry-Snapshot([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return '<missing>' }
    $Item = Get-ItemProperty -LiteralPath $Path
    $Values = [ordered]@{}
    foreach ($Property in @($Item.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | Sort-Object Name)) {
        if ($Property.Value -is [byte[]]) {
            $Values[$Property.Name] = [Convert]::ToBase64String($Property.Value)
        } else {
            $Values[$Property.Name] = $Property.Value
        }
    }
    return ($Values | ConvertTo-Json -Compress -Depth 6)
}

function Assert-InstalledPayload([string]$Root, $Provenance) {
    $Root = [System.IO.Path]::GetFullPath($Root)
    $Expected = @()
    foreach ($Property in $Provenance.files.PSObject.Properties) {
        $Relative = [string]$Property.Name
        $Expected += $Relative
        $Target = Join-Path $Root ($Relative -replace '/', '\\')
        if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
            Fail "Installed payload file is missing: $Relative"
        }
        $ActualHash = File-Sha256 $Target
        $ExpectedHash = ([string]$Property.Value).ToLowerInvariant()
        if ($ActualHash -ne $ExpectedHash) {
            Fail "Installed payload SHA256 mismatch: $Relative"
        }
    }

    # provenance.json deliberately cannot hash itself, but it is still part of
    # the installer payload. Inno Setup also creates uninsNNN.* files, which are
    # installer bookkeeping and not part of the portable fingerprint.
    $Expected += 'provenance.json'
    $Actual = @(
        Get-ChildItem -LiteralPath $Root -Recurse -File | ForEach-Object {
            $Relative = $_.FullName.Substring($Root.Length).TrimStart('\\') -replace '\\', '/'
            if ($Relative -notmatch '^unins\d+\.(exe|dat|msg)$') { $Relative }
        }
    )
    $Missing = @($Expected | Where-Object { $Actual -notcontains $_ })
    $Unexpected = @($Actual | Where-Object { $Expected -notcontains $_ })
    if ($Missing.Count -gt 0) {
        Fail ('Installed payload is missing fingerprinted files: ' + ($Missing -join ', '))
    }
    if ($Unexpected.Count -gt 0) {
        Fail ('Installed payload contains unexpected files: ' + ($Unexpected -join ', '))
    }
    return $Expected.Count
}

$InstallerPath = [System.IO.Path]::GetFullPath($InstallerPath)
$SourceDist = [System.IO.Path]::GetFullPath($SourceDist)
if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { Fail 'Installer not found.' }
if (-not (Test-Path -LiteralPath $SourceDist -PathType Container)) { Fail 'Source dist not found.' }

$SourceProvenancePath = Join-Path $SourceDist 'provenance.json'
$SourceProvenance = Read-Json $SourceProvenancePath
if ($SourceProvenance.product -ne 'Ultra Stalker Desktop' -or $SourceProvenance.developer -ne 'Ahmed L-HadarY') {
    Fail 'Source provenance identity mismatch.'
}
if ($SourceProvenance.platform -ne 'windows-x64') { Fail 'Source provenance is not Windows x64.' }
if (-not $SourceProvenance.build_id) { Fail 'Source provenance Build ID is missing.' }

if (-not $OutputPath) {
    $OutputPath = Join-Path (Split-Path -Parent $InstallerPath) 'INSTALLER_SMOKE_TEST.json'
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$OutputDir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue

$SmokeId = [Guid]::NewGuid().ToString('N')
$SmokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("UltraStalker-Smoke-$SmokeId")
$ProductionAppId = '{8B1EF58E-7E5F-4D2F-9BC5-7A5D0C1E2026}'
$UninstallRoot = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
$ProductionUninstallKey = Join-Path $UninstallRoot ($ProductionAppId + '_is1')
$SmokeAppId = $ProductionAppId + '-smoke-' + $SmokeId
$SmokeUninstallKey = Join-Path $UninstallRoot ($SmokeAppId + '_is1')
$ProductionRegistryBefore = Registry-Snapshot $ProductionUninstallKey
$SmokeRegistryIsolated = $false
$ProductionRegistryUnchanged = $false
$SmokeRegistryRemoved = $false
$InstallDir = Join-Path $SmokeRoot 'app'
$SmokeLocal = Join-Path $SmokeRoot 'localappdata'
$SmokeRoaming = Join-Path $SmokeRoot 'appdata'
$SetupLog = Join-Path $SmokeRoot 'setup.log'
$GroupName = "UltraStalker Desktop Smoke $SmokeId"
$UninstallAttempted = $false
$UninstallPassed = $false
$UpgradePassed = $false
$UpgradeUserDataPreserved = $false
$UpgradeStaleRuntimeCleanupPassed = $false
$UninstallUserDataPreserved = $false
$RuntimeSelfTestSha = $null
$PayloadCount = 0
$OldLocal = $env:LOCALAPPDATA
$OldRoaming = $env:APPDATA
$WindowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $WindowsPowerShell -PathType Leaf)) { Fail 'System Windows PowerShell was not found.' }

try {
    New-Item -ItemType Directory -Path $InstallDir, $SmokeLocal, $SmokeRoaming -Force | Out-Null

    $SetupArgs = @(
        '/VERYSILENT',
        '/SUPPRESSMSGBOXES',
        '/NORESTART',
        '/SP-',
        '/NOCANCEL',
        '/NOICONS',
        "/DIR=`"$InstallDir`"",
        "/GROUP=`"$GroupName`"",
        '/TASKS=',
        "/SMOKETEST=$SmokeId",
        "/LOG=`"$SetupLog`""
    )
    $InstallExitCode = Invoke-WaitedNativeProcess $InstallerPath $SetupArgs
    if ($InstallExitCode -ne 0) { Fail "Silent installer exited with code $InstallExitCode" }


    if (-not (Test-Path -LiteralPath $SmokeUninstallKey)) {
        Fail 'Smoke installer did not create its isolated uninstall registry key.'
    }
    if ((Registry-Snapshot $ProductionUninstallKey) -ne $ProductionRegistryBefore) {
        Fail 'Smoke installation modified the production uninstall registry entry.'
    }
    $SmokeRegistryIsolated = $true
    $ProductionRegistryUnchanged = $true

    $Exe = Join-Path $InstallDir 'UltraStalkerDesktop.exe'
    $InstalledProvenancePath = Join-Path $InstallDir 'provenance.json'
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { Fail 'Installed executable is missing.' }
    if (-not (Test-Path -LiteralPath $InstalledProvenancePath -PathType Leaf)) { Fail 'Installed provenance is missing.' }
    if ((File-Sha256 $InstalledProvenancePath) -ne (File-Sha256 $SourceProvenancePath)) {
        Fail 'Installer contains provenance different from the source dist.'
    }

    $InstalledProvenance = Read-Json $InstalledProvenancePath
    if ($InstalledProvenance.build_id -ne $SourceProvenance.build_id) {
        Fail 'Installed Build ID does not match the source dist.'
    }
    $PayloadCount = Assert-InstalledPayload $InstallDir $InstalledProvenance

    $env:LOCALAPPDATA = $SmokeLocal
    $env:APPDATA = $SmokeRoaming
    $InstalledVerifier = Join-Path $PSScriptRoot 'verify_installed_runtime.ps1'
    & $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File $InstalledVerifier -InstallDir $InstallDir
    if ($LASTEXITCODE -ne 0) { Fail 'Installed runtime verification failed.' }

    $RuntimeSelfTest = Join-Path $SmokeLocal 'UltraStalker\diagnostics\SELF_TEST.json'
    $RuntimeReport = Read-Json $RuntimeSelfTest
    if ($RuntimeReport.report_kind -ne 'runtime' -or -not $RuntimeReport.passed) {
        Fail 'Installed runtime self-test report did not pass.'
    }
    if (-not $RuntimeReport.checks.database_integrity -or $RuntimeReport.checks.database_integrity_status -notin @('ok', 'not_created')) {
        Fail 'Installed runtime self-test did not pass user database integrity verification.'
    }
    if (-not $RuntimeReport.checks.release_integrity) {
        Fail 'Installed runtime self-test did not pass release integrity verification.'
    }
    if ($RuntimeReport.release_integrity.status -ne 'ok') {
        Fail 'Installed runtime reported a release integrity mismatch.'
    }
    if ($RuntimeReport.release_integrity.build_id -ne $SourceProvenance.build_id) {
        Fail 'Installed runtime integrity Build ID mismatch.'
    }
    $RuntimeSelfTestSha = File-Sha256 $RuntimeSelfTest

    # The runtime test writes only to the sandboxed AppData. Every installed
    # fingerprinted byte must remain identical afterward.
    [void](Assert-InstalledPayload $InstallDir $InstalledProvenance)

    # Exercise an in-place upgrade before uninstalling. Seed both roaming and
    # local user data plus a fake obsolete PyInstaller runtime file. The second
    # installer run must preserve user data while [InstallDelete] removes the
    # stale runtime file under _internal.
    $RoamingUserDir = Join-Path $SmokeRoaming 'UltraStalker'
    $LocalUserDir = Join-Path $SmokeLocal 'UltraStalker'
    New-Item -ItemType Directory -Path $RoamingUserDir, $LocalUserDir -Force | Out-Null
    $RoamingSentinel = Join-Path $RoamingUserDir 'smoke-preserve-roaming.txt'
    $LocalSentinel = Join-Path $LocalUserDir 'smoke-preserve-local.txt'
    $SentinelValue = "UltraStalker-Smoke-UserData-$SmokeId"
    Set-Content -LiteralPath $RoamingSentinel -Value $SentinelValue -Encoding UTF8 -NoNewline
    Set-Content -LiteralPath $LocalSentinel -Value $SentinelValue -Encoding UTF8 -NoNewline

    $StaleInternal = Join-Path $InstallDir '_internal\ultrastalker-smoke-obsolete.tmp'
    New-Item -ItemType Directory -Path (Split-Path -Parent $StaleInternal) -Force | Out-Null
    Set-Content -LiteralPath $StaleInternal -Value 'obsolete-runtime' -Encoding ASCII -NoNewline
    if (-not (Test-Path -LiteralPath $StaleInternal -PathType Leaf)) {
        Fail 'Could not seed stale runtime file for upgrade smoke test.'
    }

    $UpgradeExitCode = Invoke-WaitedNativeProcess $InstallerPath $SetupArgs
    if ($UpgradeExitCode -ne 0) { Fail "Silent upgrade installer exited with code $UpgradeExitCode" }


    if (-not (Test-Path -LiteralPath $SmokeUninstallKey)) {
        Fail 'Upgrade lost the isolated smoke uninstall registry key.'
    }
    if ((Registry-Snapshot $ProductionUninstallKey) -ne $ProductionRegistryBefore) {
        Fail 'Smoke upgrade modified the production uninstall registry entry.'
    }

    foreach ($Sentinel in @($RoamingSentinel, $LocalSentinel)) {
        if (-not (Test-Path -LiteralPath $Sentinel -PathType Leaf)) {
            Fail 'Upgrade removed sandboxed user data.'
        }
        if ((Get-Content -LiteralPath $Sentinel -Raw -Encoding UTF8) -ne $SentinelValue) {
            Fail 'Upgrade modified sandboxed user data.'
        }
    }
    $UpgradeUserDataPreserved = $true

    if (Test-Path -LiteralPath $StaleInternal) {
        Fail 'Upgrade did not remove the seeded obsolete _internal runtime file.'
    }
    $UpgradeStaleRuntimeCleanupPassed = $true

    $InstalledProvenanceAfterUpgrade = Read-Json $InstalledProvenancePath
    if ($InstalledProvenanceAfterUpgrade.build_id -ne $SourceProvenance.build_id) {
        Fail 'Upgrade installed a payload with an unexpected Build ID.'
    }
    [void](Assert-InstalledPayload $InstallDir $InstalledProvenanceAfterUpgrade)
    & $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File $InstalledVerifier -InstallDir $InstallDir
    if ($LASTEXITCODE -ne 0) { Fail 'Installed runtime verification failed after upgrade.' }
    $RuntimeSelfTest = Join-Path $SmokeLocal 'UltraStalker\diagnostics\SELF_TEST.json'
    $RuntimeSelfTestSha = File-Sha256 $RuntimeSelfTest
    $UpgradePassed = $true

    $Uninstaller = Get-ChildItem -LiteralPath $InstallDir -Filter 'unins*.exe' -File | Select-Object -First 1
    if (-not $Uninstaller) { Fail 'Inno Setup uninstaller is missing after installation.' }
    $UninstallAttempted = $true
    $UninstallExitCode = Invoke-WaitedNativeProcess $Uninstaller.FullName @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    if ($UninstallExitCode -ne 0) { Fail "Silent uninstaller exited with code $UninstallExitCode" }

    for ($i = 0; $i -lt 50 -and (Test-Path -LiteralPath $Exe); $i++) {
        Start-Sleep -Milliseconds 100
    }
    if (Test-Path -LiteralPath $Exe) { Fail 'Application executable remains after silent uninstall.' }
    $UninstallPassed = $true


    if (Test-Path -LiteralPath $SmokeUninstallKey) {
        Fail 'Smoke uninstall registry key remains after uninstall.'
    }
    $SmokeRegistryRemoved = $true
    if ((Registry-Snapshot $ProductionUninstallKey) -ne $ProductionRegistryBefore) {
        Fail 'Smoke uninstall modified the production uninstall registry entry.'
    }
    $ProductionRegistryUnchanged = $true

    foreach ($Sentinel in @($RoamingSentinel, $LocalSentinel)) {
        if (-not (Test-Path -LiteralPath $Sentinel -PathType Leaf)) {
            Fail 'Uninstall removed sandboxed user data.'
        }
        if ((Get-Content -LiteralPath $Sentinel -Raw -Encoding UTF8) -ne $SentinelValue) {
            Fail 'Uninstall modified sandboxed user data.'
        }
    }
    $UninstallUserDataPreserved = $true

    $Result = [ordered]@{
        product = 'Ultra Stalker Desktop'
        version = '0.1.0'
        developer = 'Ahmed L-HadarY'
        platform = 'windows-x64'
        passed = $true
        build_id = [string]$SourceProvenance.build_id
        tested_utc = [DateTime]::UtcNow.ToString('o')
        installer_sha256 = File-Sha256 $InstallerPath
        portable_provenance_sha256 = File-Sha256 $SourceProvenancePath
        installed_payload_file_count = [int]$PayloadCount
        installed_payload_verified = $true
        runtime_self_test_passed = $true
        runtime_self_test_sha256 = [string]$RuntimeSelfTestSha
        runtime_release_integrity = 'ok'
        runtime_database_integrity = [string]$RuntimeReport.checks.database_integrity_status
        payload_immutable_after_runtime_test = $true
        smoke_registry_isolated = [bool]$SmokeRegistryIsolated
        production_registry_unchanged = [bool]$ProductionRegistryUnchanged
        smoke_registry_removed = [bool]$SmokeRegistryRemoved
        upgrade_passed = [bool]$UpgradePassed
        upgrade_user_data_preserved = [bool]$UpgradeUserDataPreserved
        upgrade_stale_runtime_cleanup_passed = [bool]$UpgradeStaleRuntimeCleanupPassed
        uninstall_passed = [bool]$UninstallPassed
        uninstall_user_data_preserved = [bool]$UninstallUserDataPreserved
    }
    $Result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    Write-Host '[PASS] Installer smoke test passed.' -ForegroundColor Green
    Write-Host ("Build ID: " + $SourceProvenance.build_id)
    exit 0
}
catch {
    Write-Host ('[FAIL] Installer smoke test: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
finally {
    $env:LOCALAPPDATA = $OldLocal
    $env:APPDATA = $OldRoaming

    # Best-effort uninstall if an earlier check failed after installation.
    if (-not $UninstallPassed -and (Test-Path -LiteralPath $InstallDir -PathType Container)) {
        $FallbackUninstaller = Get-ChildItem -LiteralPath $InstallDir -Filter 'unins*.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($FallbackUninstaller) {
            try {
                # Retry cleanup even when a normal uninstall was already attempted
                # but failed. The smoke workspace must not depend on a one-shot
                # uninstaller succeeding during an earlier assertion path.
                [void](Invoke-WaitedNativeProcess $FallbackUninstaller.FullName @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'))
            } catch { }
        }
    }
    Remove-Item -LiteralPath $SmokeRoot -Recurse -Force -ErrorAction SilentlyContinue
}
