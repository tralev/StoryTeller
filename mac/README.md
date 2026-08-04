# macOS Build Code (App B — Forge CLI)

Holds the **build code** required to build the Forge CLI for macOS.
No build outputs live here — every artifact lands under `tmp/`.

## What lives here

| File | Description |
|---|---|
| `mac/build.sh` | macOS build script (3 modes: `cli` / `--app` / `--dmg`) |
| `mac/forge.spec` | PyInstaller spec for the `forge` CLI |

## Build

```bash
# CLI binary only
bash mac/build.sh

# CLI + .app bundle
bash mac/build.sh --app

# CLI + .app + .dmg (full distributable package)
bash mac/build.sh --dmg
```

## Where outputs go

`mac/` is build code only. All outputs land under `tmp/`:

| Path | Contains |
|---|---|
| `tmp/build/` | PyInstaller work files (intermediate, discardable) |
| `tmp/dist/` | PyInstaller raw binary output |
| `tmp/packages/` | Final artifacts: `forge`, `.app`, `.dmg` |

The script builds via `pyinstaller mac/forge.spec --distpath tmp/dist --workpath tmp/build`,
then publishes the binary / `.app` / `.dmg` to `tmp/packages/`.

## Packaging

`mac/build.sh` performs three steps:

1. `pyinstaller mac/forge.spec` — builds the CLI
2. Wraps it in `StoryTeller Forge.app` (Info.plist)
3. Creates `StoryTeller Forge-<version>.dmg` via `hdiutil` (drag-to-Applications install)

Requires macOS + Xcode Command Line Tools. Binaries are gitignored (safety net);
the canonical location for built artifacts is `tmp/packages/`.

## Notes

- `mac/` → macOS build code, `lin/` → Linux build code (future), `win/` → Windows
  build code (future). Same convention everywhere: code in the directory, outputs in `tmp/`.
