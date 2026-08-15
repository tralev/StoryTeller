# Windows Build Code (App B — Forge CLI)

Holds the **build code** required to build the Forge CLI for Windows.

## Convention

Like `mac/` and `lin/`: this directory holds **build code only**. All build
outputs land under `tmp/`:

| Path | Contains |
|---|---|
| `win/build.ps1` | Windows build script |
| `win/forge.spec` | PyInstaller spec (P8.13 — exists, builds the CLI) |
| `tmp/packages/forge.exe` | Final Windows binary (once built) |

## Build

```powershell
powershell -File win/build.ps1
# publishes to tmp/packages/forge.exe
```

The build behaves exactly like `mac/build.sh` / `lin/build.sh`:

- Intermediates → `tmp/build/` + `tmp/dist/`
- Final binary → `tmp/packages/forge.exe`

Requires: Windows, Python 3.9+, pyinstaller installed in the venv
(defaults to `.venv\Scripts\python.exe`; override with `$env:VENV_PY`).
