# Windows Build Code (App B — Forge CLI)

Holds the **build code** required to build the Forge CLI for Windows.

## Convention

Like `mac/` and `lin/`: this directory holds **build code only**. All build
outputs land under `tmp/`:

| Path | Contains |
|---|---|
| `win/build.ps1` | Windows build script (placeholder — spec not created yet) |
| `win/forge.spec` | PyInstaller spec (future — `cp mac/forge.spec win/forge.spec`) |
| `tmp/packages/forge.exe` | Final Windows binary (once built) |

## Build

```powershell
powershell -File win/build.ps1
# publishes to tmp/packages/forge.exe
```

Currently a **placeholder**: the script prints the setup steps and exits 1
until `win/forge.spec` exists. Once the spec is added (it is project-root
relative via `SPECPATH`, so `mac/forge.spec` works as a starting point),
the build behaves exactly like `mac/build.sh` / `lin/build.sh`:

- Intermediates → `tmp/build/` + `tmp/dist/`
- Final binary → `tmp/packages/forge.exe`

Requires: Windows, Python 3.9+, pyinstaller installed in the venv
(defaults to `.venv\Scripts\python.exe`; override with `$env:VENV_PY`).
