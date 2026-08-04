#!/usr/bin/env bash
# Build the Forge CLI for macOS.
#
#   bash scripts/build_mac.sh            # CLI binary only
#   bash scripts/build_mac.sh --app      # CLI + .app bundle
#   bash scripts/build_mac.sh --dmg      # CLI + .app + .dmg (full package)
#
# PyInstaller intermediates (build/, dist/) land under tmp/ so the project
# root stays clean. Final artifacts are published to mac/.
#
#   tmp/build/    PyInstaller work files (intermediate, discardable)
#   tmp/dist/     PyInstaller raw binary output
#   mac/forge     Final CLI binary
#   mac/*.app     Final .app bundle
#   mac/*.dmg     Final disk image
#
# Requires: macOS, Python 3.9+, pyinstaller installed in the venv.
set -euo pipefail

cd "$(dirname "$0")/.."   # project root

VENV_PY="${VENV_PY:-.venv/bin/python}"
WORK_DIR="tmp/build"
PYI_DIST="tmp/dist"
PUBLISH_DIR="mac"
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
"$VENV_PY" -m PyInstaller forge.spec --distpath "$PYI_DIST" --workpath "$WORK_DIR" --noconfirm

# 2. Publish the binary to mac/
mkdir -p "$PUBLISH_DIR"
cp "$PYI_DIST/forge" "$PUBLISH_DIR/forge"
chmod +x "$PUBLISH_DIR/forge"
echo "==> CLI binary: $PUBLISH_DIR/forge"

# 3. (Optional) Wrap in a .app bundle
if [[ "$MODE" == "--app" || "$MODE" == "--dmg" ]]; then
    echo "==> Creating .app bundle: $PUBLISH_DIR/$APP_NAME.app"
    APP="$PUBLISH_DIR/$APP_NAME.app"
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

    cp "$PUBLISH_DIR/forge" "$APP/Contents/MacOS/forge"
    chmod +x "$APP/Contents/MacOS/forge"
    echo "==> .app bundle: $APP"
fi

# 4. (Optional) Create a .dmg disk image
if [[ "$MODE" == "--dmg" ]]; then
    echo "==> Creating .dmg: $PUBLISH_DIR/$APP_NAME-$VERSION.dmg"
    DMG="$PUBLISH_DIR/$APP_NAME-$VERSION.dmg"
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

echo "==> Done. Intermediates in tmp/build + tmp/dist, published to $PUBLISH_DIR/"
