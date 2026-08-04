#!/usr/bin/env bash
# Build the Forge CLI for Linux.
#
#   bash lin/build.sh        # CLI binary only
#
# lin/ holds BUILD CODE ONLY. Every build output lands under tmp/:
#
#   tmp/build/        PyInstaller work files (intermediate, discardable)
#   tmp/dist/         PyInstaller raw binary output
#   tmp/packages/     Final artifacts: forge binary
#
# Requires: Linux, Python 3.9+, pyinstaller installed in the venv.
#
# NOTE: Placeholder — `lin/forge.spec` does not exist yet. Running this
# script prints the steps to create it, then exits 1. Once the spec is
# in place, the script builds exactly like mac/build.sh.
set -euo pipefail

cd "$(dirname "$0")/.."   # project root

VENV_PY="${VENV_PY:-.venv/bin/python}"
SPEC="lin/forge.spec"
WORK_DIR="tmp/build"
PYI_DIST="tmp/dist"
PACKAGES_DIR="tmp/packages"

echo "==> Building Forge CLI (Linux)"

if [[ ! -f "$SPEC" ]]; then
    echo ""
    echo "Not implemented yet: $SPEC does not exist."
    echo ""
    echo "To enable the Linux build:"
    echo "  1. cp mac/forge.spec $SPEC"
    echo "  2. Review the spec — paths are project-root relative via SPECPATH,"
    echo "     so it should work as-is on Linux."
    echo "  3. Re-run: bash lin/build.sh"
    echo ""
    echo "Exiting (placeholder)."
    exit 1
fi

# Ensure pyinstaller is available
if ! "$VENV_PY" -c "import PyInstaller" 2>/dev/null; then
    echo "    Installing pyinstaller..."
    "$VENV_PY" -m pip install pyinstaller -q
fi

# 1. Build the CLI binary into tmp/dist/ (raw PyInstaller output)
"$VENV_PY" -m PyInstaller "$SPEC" --distpath "$PYI_DIST" --workpath "$WORK_DIR" --noconfirm

# 2. Publish the binary to tmp/packages/
mkdir -p "$PACKAGES_DIR"
cp "$PYI_DIST/forge" "$PACKAGES_DIR/forge"
chmod +x "$PACKAGES_DIR/forge"
echo "==> CLI binary: $PACKAGES_DIR/forge"

echo "==> Done. Intermediates in tmp/build + tmp/dist, artifact in $PACKAGES_DIR/"
