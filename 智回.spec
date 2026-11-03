# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件 + 无控制台窗口。

构建：
    pyinstaller 智回.spec --clean --noconfirm
产物：
    dist/智回.exe
"""
import os

ROOT = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "web"), "web"),
        (os.path.join(ROOT, "assets", "app.ico"), "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 本项目是纯标准库实现，这些重型三方库一律排除，能显著缩小体积
    excludes=[
        "numpy", "pandas", "scipy", "matplotlib", "PIL", "Pillow",
        "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
        "setuptools", "pkg_resources", "pip", "wheel",
        "pytest", "sqlalchemy", "requests", "lxml", "openpyxl",
    ],
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
    name="智回",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 无控制台，双击直接弹控制窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "app.ico"),
    version=os.path.join(ROOT, "version_info.txt"),
)
