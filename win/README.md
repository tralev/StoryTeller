# Windows Build Code (App B — Forge CLI)

Holds the **build code** required to build the Forge CLI for Windows.
Currently a placeholder — no Windows build script exists yet.

## Convention

Like `mac/` and `lin/`: this directory holds **build code only**. All build
outputs land under `tmp/`:

| Path | Contains |
|---|---|
| `win/build.ps1` | Windows build script (future) |
| `win/forge.spec` | PyInstaller spec (future) |
| `tmp/packages/forge.exe` | Final Windows binary (once built) |

## Future build (once the spec exists)

```powershell
powershell -File win/build.ps1
# publishes to tmp/packages/forge.exe
```

Intermediates live under `tmp/build/` + `tmp/dist/`; the final executable is
published to `tmp/packages/`.
