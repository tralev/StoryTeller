# Linux Build Code (App B — Forge CLI)

Holds the **build code** required to build the Forge CLI for Linux.
Currently a placeholder — no Linux build script exists yet.

## Convention

Like `mac/` and `win/`: this directory holds **build code only**. All build
outputs land under `tmp/`:

| Path | Contains |
|---|---|
| `lin/build.sh` | Linux build script (future) |
| `lin/forge.spec` | PyInstaller spec (future) |
| `tmp/packages/forge` | Final Linux binary (once built) |

## Future build (once the spec exists)

```bash
bash lin/build.sh
# publishes to tmp/packages/forge
```

Intermediates live under `tmp/build/` + `tmp/dist/`; the final executable is
published to `tmp/packages/`.
