#!/usr/bin/env bash
# Build the Forge CLI for macOS.
#
#   bash mac/build.sh            # CLI binary only
#   bash mac/build.sh --app      # CLI + .app bundle
#   bash mac/build.sh --dmg      # CLI + .app + .dmg (full package)
#
# mac/ holds BUILD CODE ONLY. Every build output lands under tmp/:
#
#   tmp/build/        PyInstaller work files (intermediate, discardable)
#   tmp/dist/         PyInstaller raw binary output
#   tmp/packages/     Final artifacts: forge binary, .app, .dmg
#
# Requires: macOS, Python 3.9+, pyinstaller installed in the venv.
set -euo pipefail

cd "$(dirname "$0")/.."   # project root

VENV_PY="${VENV_PY:-.venv/bin/python}"
SPEC="mac/forge.spec"
WORK_DIR="tmp/build"
PYI_DIST="tmp/dist"
PACKAGES_DIR="tmp/packages"
APP_NAME="StoryTeller Forge"
VERSION="0.1.0"

MODE="${1:-cli}"

echo "==> Building Forge CLI ($MODE mode)"

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

# 3. (Optional) Wrap in a .app bundle
if [[ "$MODE" == "--app" || "$MODE" == "--dmg" ]]; then
    echo "==> Creating .app bundle: $PACKAGES_DIR/$APP_NAME.app"
    APP="$PACKAGES_DIR/$APP_NAME.app"
    rm -rf "$APP"
    mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

    # Info.plist
    cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>$APP_NAME</string>
    <key>CFBundleDisplayName</key><string>$APP_NAME</string>
    <key>CFBundleIdentifier</key><string>com.storyteller.forge</string>
    <key>CFBundleVersion</key><string>$VERSION</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleExecutable</key><string>forge</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict>
</plist>
EOF

    cp "$PACKAGES_DIR/forge" "$APP/Contents/MacOS/forge"
    chmod +x "$APP/Contents/MacOS/forge"
    echo "==> .app bundle: $APP"
fi

# 4. (Optional) Create a .dmg disk image
if [[ "$MODE" == "--dmg" ]]; then
    echo "==> Creating .dmg: $PACKAGES_DIR/$APP_NAME-$VERSION.dmg"
    DMG="$PACKAGES_DIR/$APP_NAME-$VERSION.dmg"
    STAGE="$WORK_DIR/dmg_stage"
    rm -rf "$STAGE"
    mkdir -p "$STAGE"
    cp -R "$APP" "$STAGE/"
    # Symlink to /Applications for drag-to-install
    ln -s /Applications "$STAGE/Applications"

    hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
    rm -rf "$STAGE"
    echo "==> .dmg: $DMG"
fi

echo "==> Done. Intermediates in tmp/build + tmp/dist, artifacts in $PACKAGES_DIR/"
