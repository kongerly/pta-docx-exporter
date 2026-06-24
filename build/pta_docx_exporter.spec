# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


project_root = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(project_root))

from app_meta import APP_ID

runtime_root = project_root / "runtime"
datas = [(str(project_root / "pta" / "browser_service.js"), "pta")]

if runtime_root.exists():
    datas.append((str(runtime_root), "runtime"))

hiddenimports = ["lxml", "lxml.html", "docx", "PIL"]

block_cipher = None

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_ID,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_ID,
)
