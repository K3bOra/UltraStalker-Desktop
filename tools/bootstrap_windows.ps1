$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$MpvVersion = '0.41.0'
$MpvArchiveSha256 = '4e197f729f5071c6772f35fffd96e0f36e3e8a044bd9479b136bb09b7c6a80ff'
$WindowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $WindowsPowerShell -PathType Leaf)) { throw 'System Windows PowerShell was not found.' }

function Step([string]$Text) { Write-Host "[STEP] $Text" -ForegroundColor Cyan }
function Ok([string]$Text) { Write-Host "[OK] $Text" -ForegroundColor Green }

function Test-MpvVendor {
    $Exe = Join-Path $Root 'vendor\mpv\mpv.exe'
    $MetaPath = Join-Path $Root 'vendor\mpv\ULTRASTALKER_MPV_PROVENANCE.json'
    if (-not (Test-Path $Exe) -or -not (Test-Path $MetaPath)) { return $false }
    try {
        $Meta = Get-Content -Raw -Encoding UTF8 $MetaPath | ConvertFrom-Json
        if ([string]$Meta.version -ne $MpvVersion) { return $false }
        if (([string]$Meta.archive_sha256).ToLowerInvariant() -ne $MpvArchiveSha256) { return $false }
        if (-not $Meta.executable_sha256) { return $false }
        $ActualExe = (Get-FileHash -Algorithm SHA256 -Path $Exe).Hash.ToLowerInvariant()
        if ($ActualExe -ne ([string]$Meta.executable_sha256).ToLowerInvariant()) { return $false }
        return $true
    } catch {
        return $false
    }
}

Step 'Checking Windows host'
if ($env:OS -ne 'Windows_NT') { throw 'This build pipeline must run on Windows.' }

Step 'Locating Python 3.11+'
$ProbePath = Join-Path $env:TEMP ("ultrastalker-python-probe-" + [Guid]::NewGuid().ToString('N') + '.py')
$ProbeCode = @'
import platform
import struct
import sys

bits = struct.calcsize("P") * 8
valid = (
    platform.python_implementation() == "CPython"
    and (3, 11) <= sys.version_info[:2] < (3, 15)
    and bits == 64
)
print(
    "implementation=%s version=%s bits=%s executable=%s"
    % (platform.python_implementation(), platform.python_version(), bits, sys.executable)
)
raise SystemExit(0 if valid else 1)
'@
[System.IO.File]::WriteAllText($ProbePath, $ProbeCode, [System.Text.Encoding]::ASCII)

$Candidates = @()
if ($env:ULTRASTALKER_PYTHON_EXE) {
    $Candidates += [PSCustomObject]@{ Exe = [string]$env:ULTRASTALKER_PYTHON_EXE; Args = @() }
}
if ($env:pythonLocation) {
    $Candidates += [PSCustomObject]@{ Exe = (Join-Path $env:pythonLocation 'python.exe'); Args = @() }
}
if ($env:Python3_ROOT_DIR) {
    $Candidates += [PSCustomObject]@{ Exe = (Join-Path $env:Python3_ROOT_DIR 'python.exe'); Args = @() }
}
$PythonCommand = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($PythonCommand -and $PythonCommand.Source) {
    $Candidates += [PSCustomObject]@{ Exe = [string]$PythonCommand.Source; Args = @() }
}
$Candidates += @(
    [PSCustomObject]@{ Exe = 'python.exe'; Args = @() },
    [PSCustomObject]@{ Exe = 'py.exe'; Args = @('-3.13') },
    [PSCustomObject]@{ Exe = 'py.exe'; Args = @('-3.12') },
    [PSCustomObject]@{ Exe = 'py.exe'; Args = @('-3.14') },
    [PSCustomObject]@{ Exe = 'py.exe'; Args = @('-3.11') }
)

$ChosenExe = $null
$ChosenArgs = @()
try {
    foreach ($c in $Candidates) {
        $Exe = [string]$c.Exe
        $PythonArgs = @()
        if ($null -ne $c.Args) { $PythonArgs = [string[]]@($c.Args) }
        if ([string]::IsNullOrWhiteSpace($Exe)) { continue }

        $LooksLikePath = $Exe.Contains('\') -or $Exe.Contains('/')
        if ($LooksLikePath) {
            if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
                Write-Host "[INFO] Python candidate missing: $Exe"
                continue
            }
        }
        elseif (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) {
            Write-Host "[INFO] Python command unavailable: $Exe $($PythonArgs -join ' ')"
            continue
        }

        try {
            Write-Host "[INFO] Probing Python candidate: $Exe $($PythonArgs -join ' ')"
            $ProbeOutput = @(& $Exe @PythonArgs $ProbePath 2>&1)
            $ProbeExit = $LASTEXITCODE
            foreach ($Line in $ProbeOutput) { Write-Host "[PYTHON] $Line" }
            if ($ProbeExit -eq 0) {
                $ChosenExe = $Exe
                $ChosenArgs = $PythonArgs
                break
            }
            Write-Host "[INFO] Python candidate rejected with exit code $ProbeExit"
        }
        catch {
            Write-Host ("[INFO] Python candidate failed: " + $_.Exception.GetType().Name)
        }
    }
}
finally {
    Remove-Item -LiteralPath $ProbePath -Force -ErrorAction SilentlyContinue
}
if (-not $ChosenExe) { throw '64-bit CPython 3.11-3.14 was not found.' }
Ok ("Using " + $ChosenExe + " " + ($ChosenArgs -join ' '))
$ChosenPythonVersion = (& $ChosenExe @ChosenArgs -c 'import platform; print(platform.python_version())').Trim()
if (-not $ChosenPythonVersion) { throw 'Could not determine the selected CPython version.' }

Step 'Verifying frozen source tree'
& $ChosenExe @ChosenArgs tools\source_freeze.py --root .
if ($LASTEXITCODE -ne 0) { throw 'Source freeze verification failed. Regenerate SOURCE_FREEZE.json only after a complete source audit.' }
Ok 'Frozen source tree verified'

$BuildState = Join-Path $Root '.buildstate'
$DependencyLock = Join-Path $BuildState 'WINDOWS_DEPENDENCY_LOCK.txt'
if (Test-Path $BuildState) { Remove-Item -Recurse -Force $BuildState }
New-Item -ItemType Directory -Force $BuildState | Out-Null

function New-IsolatedVenv {
    if (Test-Path '.venv') { Remove-Item -Recurse -Force '.venv' }
    & $ChosenExe @ChosenArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    $Python = Join-Path $Root '.venv\Scripts\python.exe'
    & $Python -c 'import platform,struct,sys; raise SystemExit(0 if platform.python_implementation()=="CPython" and (3,11) <= sys.version_info[:2] < (3,15) and struct.calcsize("P") * 8 == 64 else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Build venv is not supported 64-bit CPython 3.11-3.14.' }
    $VenvVersion = (& $Python -c 'import platform; print(platform.python_version())').Trim()
    if ($VenvVersion -ne $ChosenPythonVersion) { throw 'Build venv Python version changed from the selected base interpreter.' }
    return $Python
}

Step 'Resolving exact Windows release dependency set'
$Vpy = New-IsolatedVenv
& $Vpy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed.' }
& $Vpy -m pip install -r requirements-release.txt
if ($LASTEXITCODE -ne 0) { throw 'Pinned release dependency resolution failed.' }
& $Vpy -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Resolved dependency consistency check failed.' }
& $Vpy -m pip freeze | Set-Content -Encoding UTF8 $DependencyLock
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $DependencyLock)) { throw 'Dependency lock capture failed.' }
$LockText = Get-Content -Raw -Encoding UTF8 $DependencyLock
$NormalizedLock = $LockText.Replace('\','/').ToLowerInvariant()
if ($NormalizedLock -match '@\s*file:' -or $NormalizedLock -match '^-e\s' -or $NormalizedLock -match '/users/' -or $NormalizedLock -match '/home/') {
    throw 'Resolved dependency lock contains a local/direct build-machine dependency.'
}
$InvalidLockLines = @(Get-Content -Encoding UTF8 $DependencyLock | Where-Object { $_.Trim() -and $_.Trim() -notmatch '^[A-Za-z0-9_.-]+==[^\s]+$' })
if ($InvalidLockLines.Count -ne 0) { throw 'Resolved dependency lock contains non-version-pinned dependencies.' }

Step 'Rebuilding final venv from exact dependency lock'
$Vpy = New-IsolatedVenv
& $Vpy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed for locked environment.' }
& $Vpy -m pip install -r $DependencyLock
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }
& $Vpy -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency consistency check failed.' }
$Expected = @(Get-Content -Encoding UTF8 $DependencyLock | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Sort-Object)
$Actual = @(& $Vpy -m pip freeze | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Sort-Object)
$Diff = @(Compare-Object -ReferenceObject $Expected -DifferenceObject $Actual)
if ($Diff.Count -ne 0) { throw 'Final build environment does not exactly match the resolved dependency lock.' }
Ok 'Exact locked Python build environment ready'

if (-not (Test-MpvVendor)) {
    Step 'Fetching/refreshing verified mpv runtime'
    & $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File tools\fetch_mpv.ps1
    if ($LASTEXITCODE -ne 0) { throw 'mpv preparation failed.' }
}
if (-not (Test-MpvVendor)) {
    throw 'mpv vendor verification failed after preparation.'
}
Ok 'Verified mpv runtime ready'
