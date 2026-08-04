# Linux Build Code (App B — Forge CLI)

Holds the **build code** required to build the Forge CLI for Linux.

## Convention

Like `mac/` and `win/`: this directory holds **build code only**. All build
outputs land under `tmp/`:

| Path | Contains |
|---|---|
| `lin/build.sh` | Linux build script (placeholder — spec not created yet) |
| `lin/forge.spec` | PyInstaller spec (future — `cp mac/forge.spec lin/forge.spec`) |
| `tmp/packages/forge` | Final Linux binary (once built) |

## Build

```bash
bash lin/build.sh
# publishes to tmp/packages/forge
```

Currently a **placeholder**: the script prints the setup steps and exits 1
until `lin/forge.spec` exists. Once the spec is added (it is project-root
relative via `SPECPATH`, so `mac/forge.spec` works as a starting point),
the build behaves exactly like `mac/build.sh`:

- Intermediates → `tmp/build/` + `tmp/dist/`
- Final binary → `tmp/packages/forge`

Requires: Linux, Python 3.9+, pyinstaller installed in the venv.
