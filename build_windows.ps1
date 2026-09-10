param([string]$PythonExe = '')

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$App = 'UltraStalkerDesktop'
$Vpy = Join-Path $Root '.venv\Scripts\python.exe'
$WindowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $WindowsPowerShell -PathType Leaf)) { throw 'System Windows PowerShell was not found.' }

function Step([string]$Text) { Write-Host "[STEP] $Text" -ForegroundColor Cyan }
function Ok([string]$Text) { Write-Host "[OK] $Text" -ForegroundColor Green }

Step 'Bootstrapping Windows build environment'
$BootstrapArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $Root 'tools\bootstrap_windows.ps1'))
if (-not [string]::IsNullOrWhiteSpace($PythonExe)) { $BootstrapArgs += @('-PythonExe', $PythonExe) }
& $WindowsPowerShell @BootstrapArgs
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap failed.' }

Step 'Running static release gate'
& $Vpy tools\release_gate.py --root .
if ($LASTEXITCODE -ne 0) { throw 'Static release gate failed.' }

Step 'Running unit tests'
& $Vpy -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed.' }

foreach ($dir in @('build','dist','release')) {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
}
New-Item -ItemType Directory -Force release | Out-Null

Step 'Building Windows application with PyInstaller'
& $Vpy -m PyInstaller --noconfirm --clean UltraStalkerDesktop.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

Step 'Adding verified mpv runtime'
Copy-Item -Path 'vendor\mpv\mpv.exe' -Destination "dist\$App\mpv.exe" -Force
Copy-Item -Path 'vendor\mpv\ULTRASTALKER_MPV_PROVENANCE.json' -Destination "dist\$App\MPV_PROVENANCE.json" -Force
if (-not (Test-Path "dist\$App\mpv.exe")) { throw 'mpv.exe missing after payload assembly.' }

Step 'Adding third-party notices and runtime license metadata'
Copy-Item -Path 'THIRD_PARTY_NOTICES.txt' -Destination "dist\$App\THIRD_PARTY_NOTICES.txt" -Force
Copy-Item -Path 'licenses' -Destination "dist\$App\licenses" -Recurse -Force
& $Vpy tools\collect_runtime_licenses.py "dist\$App\licenses\python"
if ($LASTEXITCODE -ne 0) { throw 'Runtime license collection failed.' }
& $Vpy tools\collect_python_runtime_license.py "dist\$App\licenses"
if ($LASTEXITCODE -ne 0) { throw 'CPython runtime license collection failed.' }

Step 'Running packaged executable self-test'
$BuildSelfTestMarker = "dist\$App\.ultrastalker-build-self-test"
$BuildSelfTestNonce = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
$env:ULTRASTALKER_RELEASE_BUILD_SELF_TEST = $BuildSelfTestNonce
Set-Content -Path $BuildSelfTestMarker -Value $BuildSelfTestNonce -Encoding ASCII -NoNewline
try {
    & "dist\$App\$App.exe" --self-test-build
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path "dist\$App\SELF_TEST.json") { Get-Content "dist\$App\SELF_TEST.json" }
        throw 'Packaged executable self-test failed.'
    }
}
finally {
    Remove-Item Env:ULTRASTALKER_RELEASE_BUILD_SELF_TEST -ErrorAction SilentlyContinue
    Remove-Item $BuildSelfTestMarker -Force -ErrorAction SilentlyContinue
}
if (Test-Path $BuildSelfTestMarker) { throw 'Transient build self-test marker was not removed.' }

Step 'Capturing build environment'
& $Vpy --version 2>&1 | Set-Content -Encoding ASCII "dist\$App\PYTHON_VERSION.txt"
& $Vpy -m pip freeze | Set-Content -Encoding UTF8 "dist\$App\BUILD_DEPENDENCIES.txt"
if (-not (Test-Path '.buildstate\WINDOWS_DEPENDENCY_LOCK.txt')) { throw 'Resolved Windows dependency lock is missing.' }
Copy-Item '.buildstate\WINDOWS_DEPENDENCY_LOCK.txt' "dist\$App\WINDOWS_DEPENDENCY_LOCK.txt" -Force

Step 'Fingerprinting portable payload'
& $Vpy tools\release_fingerprint.py "dist\$App"
if ($LASTEXITCODE -ne 0) { throw 'Fingerprint generation failed.' }
& $Vpy tools\release_gate.py --root . --dist "dist\$App"
if ($LASTEXITCODE -ne 0) { throw 'Distribution release gate failed.' }

$Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $Iscc) {
    $Known = @(
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if ($Known) { $Iscc = Get-Item $Known }
}

if (-not $Iscc) {
    throw 'Inno Setup 6 or 7 was not found. Final Windows release requires an installer; install Inno Setup and rerun build_windows.bat.'
}

Step 'Building installer with Inno Setup'
& $Iscc.FullName 'installer\UltraStalkerDesktop.iss'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup build failed.' }

$Installers = @(Get-ChildItem 'release\UltraStalkerDesktop_Setup_*.exe')
if ($Installers.Count -ne 1) { throw "Expected exactly one installer, found $($Installers.Count)." }

Step 'Smoke-testing installed Windows release'
& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File tools\smoke_installer.ps1 -InstallerPath $Installers[0].FullName -SourceDist "dist\$App" -OutputPath 'release\INSTALLER_SMOKE_TEST.json'
if ($LASTEXITCODE -ne 0) { throw 'Installer smoke test failed.' }
if (-not (Test-Path 'release\INSTALLER_SMOKE_TEST.json')) { throw 'INSTALLER_SMOKE_TEST.json missing.' }

Step 'Finalizing installer release manifest'
& $Vpy tools\finalize_release.py "dist\$App" $Installers[0].FullName
if ($LASTEXITCODE -ne 0) { throw 'Final release manifest generation failed.' }
if (-not (Test-Path 'release\FINAL_RELEASE.json')) { throw 'FINAL_RELEASE.json missing.' }
Copy-Item 'tools\verify_final_release.ps1' 'release\VERIFY_RELEASE.ps1' -Force
Copy-Item 'tools\verify_installed_runtime.ps1' 'release\VERIFY_INSTALLED.ps1' -Force
Copy-Item 'WINDOWS_ACCEPTANCE.md' 'release\WINDOWS_ACCEPTANCE.md' -Force
Ok 'Ultra Stalker Desktop Windows release completed.'
