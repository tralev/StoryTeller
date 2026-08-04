# Linux Build Code (App B — Forge CLI)

Holds the **build code** required to build the Forge CLI for Linux.

## Convention

Like `mac/` and `win/`: this directory holds **build code only**. All build
outputs land under `tmp/`:

| Path | Contains |
|---|---|
| `lin/build.sh` | Linux build script |
| `lin/forge.spec` | PyInstaller spec (copy of `mac/forge.spec` — platform-agnostic) |
| `tmp/packages/forge` | Final Linux binary (once built on Linux) |

## Build

```bash
bash lin/build.sh
# publishes to tmp/packages/forge
```

The build behaves exactly like `mac/build.sh`:

- Intermediates → `tmp/build/` + `tmp/dist/`
- Final binary → `tmp/packages/forge`

Requires: **Linux**, Python 3.9+, pyinstaller installed in the venv.

> Note: PyInstaller builds for the *host* platform. Running `bash lin/build.sh`
> on macOS produces a macOS binary — run it on a Linux machine (or CI runner)
> to get the Linux binary. The spec itself is platform-agnostic (verified:
> builds cleanly from `lin/forge.spec` on any host).
