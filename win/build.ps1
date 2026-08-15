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
# P8.13: win/forge.spec exists — builds the Windows CLI binary.
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
    Write-Host "FATAL: $Spec is missing — expected to be present per P8.13."
    Write-Host "Run: cp lin/forge.spec win/forge.spec (or mac/forge.spec)"
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
