# Build the Forge CLI for Windows.
#
#   powershell -File win/build.ps1        # CLI binary only
#
# win/ holds BUILD CODE ONLY. Every build output lands under tmp/:
#
#   tmp/build/        PyInstaller work files (intermediate, discardable)
#   tmp/dist/         PyInstaller raw binary output
#   tmp/packages/     Final artifacts: forge.exe
#
# Requires: Windows, Python 3.9+, pyinstaller installed in the venv.
#
# NOTE: Placeholder — `win/forge.spec` does not exist yet. Running this
# script prints the steps to create it, then exits 1. Once the spec is
# in place, the script builds exactly like mac/build.sh / lin/build.sh.
$ErrorActionPreference = "Stop"

# Project root (parent of this script's directory)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Default to the Windows venv layout; allow override via env var
$VenvPy = $env:VENV_PY
if (-not $VenvPy) {
    $VenvPy = ".venv\Scripts\python.exe"
}
$Spec = "win\forge.spec"
$WorkDir = "tmp\build"
$PyiDist = "tmp\dist"
$PackagesDir = "tmp\packages"

Write-Host "==> Building Forge CLI (Windows)"

if (-not (Test-Path $Spec)) {
    Write-Host ""
    Write-Host "Not implemented yet: $Spec does not exist."
    Write-Host ""
    Write-Host "To enable the Windows build:"
    Write-Host "  1. cp mac/forge.spec $Spec"
    Write-Host "  2. Review the spec - paths are project-root relative via SPECPATH,"
    Write-Host "     so it should work as a starting point on Windows."
    Write-Host "     (Adjust the exe name / icon if desired.)"
    Write-Host "  3. Re-run: powershell -File win/build.ps1"
    Write-Host ""
    Write-Host "Exiting (placeholder)."
    exit 1
}

# Ensure pyinstaller is available
$pyHasPyInstaller = & $VenvPy -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Installing pyinstaller..."
    & $VenvPy -m pip install pyinstaller -q
    if ($LASTEXITCODE -ne 0) { throw "Failed to install pyinstaller" }
}

# 1. Build the CLI binary into tmp/dist/ (raw PyInstaller output)
& $VenvPy -m PyInstaller $Spec --distpath $PyiDist --workpath $WorkDir --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

# 2. Publish the binary to tmp/packages/
New-Item -ItemType Directory -Force -Path $PackagesDir | Out-Null
Copy-Item "$PyiDist\forge.exe" "$PackagesDir\forge.exe" -Force
Write-Host "==> CLI binary: $PackagesDir\forge.exe"

Write-Host "==> Done. Intermediates in tmp/build + tmp/dist, artifact in $PackagesDir/"
