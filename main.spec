# -*- mode: python ; coding: utf-8 -*-

import os
import sys


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('art/app/*', 'art/app')],
    hiddenimports=['PySide6'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['readline', '_readline'],
    noarchive=False,
    optimize=0,
)
if sys.platform.startswith("linux"):
    a.binaries = [
        entry
        for entry in a.binaries
        if not os.path.basename(entry[0]).startswith("libreadline.so")
    ]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Linework',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
