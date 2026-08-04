# Linux Native Launcher (future)

Holds the Linux build of the Forge CLI binary (`lin/forge`), produced by
PyInstaller. Currently a placeholder — no Linux binary is built yet.

To build the Forge CLI with PyInstaller (on Linux):

```bash
pyinstaller forge.spec --distpath tmp/dist --workpath tmp/build
cp tmp/dist/forge lin/forge
```

PyInstaller intermediates live under `tmp/build/` + `tmp/dist/`; the final
executable is published to `lin/forge`.
