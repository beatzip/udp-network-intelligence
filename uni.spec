# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\User\\Desktop\\A2S\\src\\uni\\app\\main.py'],
    pathex=['C:\\Users\\User\\Desktop\\A2S\\src'],
    binaries=[],
    datas=[('C:\\Users\\User\\Desktop\\A2S\\uni.toml', '.'), ('C:\\Users\\User\\Desktop\\A2S\\src\\uni\\view\\resources\\styles', 'uni/view/resources/styles'), ('C:\\Users\\User\\Desktop\\A2S\\src\\uni\\plugins\\builtins', 'uni/plugins/builtins')],
    hiddenimports=['PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui', 'pyqtgraph', 'numpy'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='uni',
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
