# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Forge CLI (Windows).
# Lives in win/ (build code home). All source paths are resolved relative
# to the project root (one level above this spec) via SPECPATH.
#
# This is a copy of mac/forge.spec — the spec is platform-agnostic
# (project-root-relative paths, no mac-only directives), so it builds
# as-is on Windows. The codesign/entitlements EXE args are None and are
# ignored by PyInstaller on non-macOS hosts.

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # project root


a = Analysis(
    [str(ROOT / 'src' / 'cli.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'config'), 'config'),
        (str(ROOT / 'src' / 'prompts'), 'src/prompts'),
        (str(ROOT / 'schemas'), 'schemas'),
    ],
    # src.application / src.pipeline / src.worldgen are imported via
    # function-local imports in generate_story — pinned as safety net.
    hiddenimports=['src', 'src.config', 'src.models', 'src.backends', 'src.validators', 'src.storage', 'src.job_queue', 'src.artifact_store', 'src.normalizer', 'src.interfaces', 'src.application', 'src.pipeline', 'src.worldgen'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # P8.13: ai_models must never be bundled — directory is gitignored.
    # matplotlib is a transitive dep of music21 but Forge never uses it at
    # runtime — excluding it avoids a broken matplotlib runtime hook and
    # shrinks the binary significantly.
    excludes=['matplotlib', 'tkinter', 'IPython', 'pandas', 'scipy', 'numpy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='forge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
