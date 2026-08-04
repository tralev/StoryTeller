#!/usr/bin/env bash
# Build the Forge CLI for macOS — outputs to mac/ (never dist/).
#
#   bash scripts/build_mac.sh            # CLI binary only
#   bash scripts/build_mac.sh --app      # CLI + .app bundle
#   bash scripts/build_mac.sh --dmg      # CLI + .app + .dmg (full package)
#
# Requires: macOS, Python 3.9+, pyinstaller installed in the venv.
set -euo pipefail

cd "$(dirname "$0")/.."   # project root

VENV_PY="${VENV_PY:-.venv/bin/python}"
DIST_DIR="mac"
WORK_DIR="build"
APP_NAME="StoryTeller Forge"
VERSION="0.1.0"

MODE="${1:-cli}"

echo "==> Building Forge CLI ($MODE mode)"

# Ensure pyinstaller is available
if ! "$VENV_PY" -c "import PyInstaller" 2>/dev/null; then
    echo "    Installing pyinstaller..."
    "$VENV_PY" -m pip install pyinstaller -q
fi

# 1. Build the CLI binary into mac/
"$VENV_PY" -m PyInstaller forge.spec --distpath "$DIST_DIR" --workpath "$WORK_DIR" --noconfirm

echo "==> CLI binary: $DIST_DIR/forge"

# 2. (Optional) Wrap in a .app bundle
if [[ "$MODE" == "--app" || "$MODE" == "--dmg" ]]; then
    echo "==> Creating .app bundle: $DIST_DIR/$APP_NAME.app"
    APP="$DIST_DIR/$APP_NAME.app"
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

    cp "$DIST_DIR/forge" "$APP/Contents/MacOS/forge"
    chmod +x "$APP/Contents/MacOS/forge"
    echo "==> .app bundle: $APP"
fi

# 3. (Optional) Create a .dmg disk image
if [[ "$MODE" == "--dmg" ]]; then
    echo "==> Creating .dmg: $DIST_DIR/$APP_NAME-$VERSION.dmg"
    DMG="$DIST_DIR/$APP_NAME-$VERSION.dmg"
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

echo "==> Done. Artifacts in $DIST_DIR/"
