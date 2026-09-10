param(
    [string]$ReleaseDir = (Join-Path (Split-Path -Parent $PSScriptRoot) 'release')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ManifestPath = Join-Path $ReleaseDir 'FINAL_RELEASE.json'
if (-not (Test-Path $ManifestPath)) { throw "FINAL_RELEASE.json not found in $ReleaseDir" }
$Manifest = Get-Content -Raw -Encoding UTF8 $ManifestPath | ConvertFrom-Json

if ($Manifest.product -ne 'Ultra Stalker Desktop') { throw 'Unexpected product in release manifest.' }
if ($Manifest.developer -ne 'Ahmed L-HadarY') { throw 'Unexpected developer in release manifest.' }
if ($Manifest.version -ne '0.1.0') { throw 'Unexpected version in release manifest.' }
if ($Manifest.reference -ne 'Ultra Stalker 8.4.1') { throw 'Unexpected reference in release manifest.' }
if ($Manifest.reference_artifact -ne 'UltraStalker_V7_UPDATE.ipk') { throw 'Unexpected reference artifact in release manifest.' }
if (-not $Manifest.self_test_passed) { throw 'Packaged Windows self-test did not pass.' }
if (-not $Manifest.installer_smoke_test_passed) { throw 'Windows installer smoke test did not pass.' }
if (-not $Manifest.build_id) { throw 'Build ID missing from release manifest.' }
if (-not $Manifest.build_environment) { throw 'Build environment identity missing from release manifest.' }
if ([string]$Manifest.source_freeze_file -ne 'SOURCE_FREEZE.json') { throw 'Unexpected source-freeze file name.' }
if ([string]$Manifest.source_tree_sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid source tree SHA256.' }
if ([string]$Manifest.source_freeze_sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid source-freeze SHA256.' }
$SourceFreezePath = Join-Path $ReleaseDir 'SOURCE_FREEZE.json'
if (-not (Test-Path -LiteralPath $SourceFreezePath -PathType Leaf)) { throw 'SOURCE_FREEZE.json is missing from the release bundle.' }
$SourceFreezeActual = (Get-FileHash -LiteralPath $SourceFreezePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($SourceFreezeActual -ne ([string]$Manifest.source_freeze_sha256).ToLowerInvariant()) { throw 'SOURCE_FREEZE.json SHA256 mismatch.' }
$SourceFreeze = Get-Content -LiteralPath $SourceFreezePath -Raw -Encoding UTF8 | ConvertFrom-Json
if (([string]$SourceFreeze.source_tree_sha256).ToLowerInvariant() -ne ([string]$Manifest.source_tree_sha256).ToLowerInvariant()) { throw 'Source tree SHA256 mismatch between freeze and final release manifest.' }
if (-not $Manifest.build_environment.python_version) { throw 'Python version missing from release manifest.' }
foreach ($Field in @('python_version_file_sha256','build_dependencies_sha256','dependency_lock_sha256','python_runtime_provenance_sha256','python_runtime_license_sha256','python_runtime_license_recorded_sha256')) {
    $Value = [string]$Manifest.build_environment.$Field
    if ($Value -notmatch '^[0-9a-fA-F]{64}$') { throw "Invalid build environment SHA256: $Field" }
}
if (([string]$Manifest.build_environment.python_runtime_license_sha256).ToLowerInvariant() -ne ([string]$Manifest.build_environment.python_runtime_license_recorded_sha256).ToLowerInvariant()) {
    throw 'CPython runtime license SHA256 does not match its recorded provenance.'
}

$Installer = Join-Path $ReleaseDir ([string]$Manifest.installer.name)
if (-not (Test-Path $Installer)) { throw "Installer missing: $Installer" }
$Actual = (Get-FileHash -Algorithm SHA256 -Path $Installer).Hash.ToLowerInvariant()
$Expected = ([string]$Manifest.installer.sha256).ToLowerInvariant()
if ($Actual -ne $Expected) { throw "Installer SHA256 mismatch. Expected $Expected, got $Actual" }

$HashFile = $Installer + '.sha256.txt'
if (-not (Test-Path $HashFile)) { throw 'Installer .sha256.txt file is missing.' }
$Recorded = ((Get-Content -Raw -Encoding ASCII $HashFile).Trim() -split '\s+')[0].ToLowerInvariant()
if ($Recorded -ne $Expected) { throw 'Installer .sha256.txt does not match FINAL_RELEASE.json.' }

$SmokePath = Join-Path $ReleaseDir 'INSTALLER_SMOKE_TEST.json'
if (-not (Test-Path -LiteralPath $SmokePath -PathType Leaf)) { throw 'INSTALLER_SMOKE_TEST.json is missing.' }
$SmokeHash = (Get-FileHash -LiteralPath $SmokePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($SmokeHash -ne ([string]$Manifest.installer_smoke_test_sha256).ToLowerInvariant()) {
    throw 'Installer smoke-test report SHA256 does not match FINAL_RELEASE.json.'
}
$Smoke = Get-Content -LiteralPath $SmokePath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Smoke.passed -or
    -not $Smoke.installed_payload_verified -or
    -not $Smoke.runtime_self_test_passed -or
    -not $Smoke.payload_immutable_after_runtime_test -or
    -not $Smoke.smoke_registry_isolated -or
    -not $Smoke.production_registry_unchanged -or
    -not $Smoke.smoke_registry_removed -or
    -not $Smoke.upgrade_passed -or
    -not $Smoke.upgrade_user_data_preserved -or
    -not $Smoke.upgrade_stale_runtime_cleanup_passed -or
    -not $Smoke.uninstall_passed -or
    -not $Smoke.uninstall_user_data_preserved) {
    throw 'Installer smoke-test report contains a failed mandatory check.'
}
if ($Smoke.build_id -ne $Manifest.build_id) { throw 'Installer smoke-test Build ID mismatch.' }
if (([string]$Smoke.installer_sha256).ToLowerInvariant() -ne $Expected) { throw 'Installer smoke-test installer SHA256 mismatch.' }
if (([string]$Smoke.portable_provenance_sha256).ToLowerInvariant() -ne ([string]$Manifest.portable_provenance_sha256).ToLowerInvariant()) {
    throw 'Installer smoke-test provenance SHA256 mismatch.'
}
if ($Smoke.runtime_release_integrity -ne 'ok') { throw 'Installer smoke-test runtime integrity did not pass.' }
if ($Smoke.runtime_database_integrity -notin @('ok', 'not_created')) { throw 'Installer smoke-test user database integrity did not pass.' }
if ($Manifest.runtime_database_integrity -ne $Smoke.runtime_database_integrity) { throw 'Runtime database-integrity evidence mismatch.' }
if (([string]$Smoke.runtime_self_test_sha256).ToLowerInvariant() -ne ([string]$Manifest.runtime_self_test_sha256).ToLowerInvariant()) {
    throw 'Installer smoke-test runtime report SHA256 mismatch.'
}

Write-Host '[PASS] Ultra Stalker Desktop release verified.' -ForegroundColor Green
Write-Host ('Version:  ' + $Manifest.version)
Write-Host ('Build ID: ' + $Manifest.build_id)
Write-Host ('SHA256:   ' + $Expected)
exit 0
