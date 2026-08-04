# Linux Native Launcher (future)

Holds the Linux build of the Forge CLI binary (`lin/forge`), produced by
PyInstaller. Currently a placeholder — no Linux binary is built yet.

To build the Forge CLI with PyInstaller (on Linux):

```bash
pyinstaller forge.spec --distpath lin
```

The resulting standalone executable lands at `lin/forge`.
