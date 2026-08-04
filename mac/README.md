# macOS Build Output (Forge CLI)

Holds macOS build artifacts for the Forge CLI. All macOS binaries and
packages land here — never in `dist/` (deprecated, removed).

## What lives here

| Artifact | Description |
|---|---|
| `mac/forge` | Standalone CLI executable (PyInstaller, arm64) |
| `mac/StoryTeller Forge.app` | macOS `.app` bundle (GUI wrapper, optional) |
| `mac/StoryTeller-Forge-<version>.dmg` | Distributable disk image (optional) |

## Build

```bash
# 1. Build the CLI binary into mac/ (one-liner)
pyinstaller forge.spec --distpath mac --workpath build

# 2. (Optional) Build the .app bundle + .dmg
bash scripts/build_mac.sh
```

The resulting binary lands at `mac/forge`.

## Packaging

`scripts/build_mac.sh` performs three steps:

1. `pyinstaller forge.spec --distpath mac --workpath build` — builds the CLI
2. Wraps it in `mac/StoryTeller Forge.app` (Info.plist + icon)
3. Creates `mac/StoryTeller-Forge.dmg` via `hdiutil` (drag-to-Applications install)

Requires macOS + Xcode Command Line Tools. Binaries are gitignored.

## Notes

- The old `dist/` directory was removed — `mac/`, `lin/`, `windows/` are the
  per-platform output homes going forward.
- `lin/` → Linux binary, `windows/` → Windows `.exe` (future).
