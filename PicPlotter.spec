# -*- mode: python ; coding: utf-8 -*-
import os
import sys

WSL_PROJECT = '\\\\wsl$\\Ubuntu\\home\\rkinder9168\\projects\\PicPlotter_auto_gpt'

ICON_PATH = f'{WSL_PROJECT}\\assets\\favicon_everline1.ico'
ICON_ARG = ICON_PATH if os.path.exists(ICON_PATH) else None

datas = [
    # Include all assets (marker icons)
    (f'{WSL_PROJECT}\\assets\\marker_outlined_transparent.png', 'assets'),
    (f'{WSL_PROJECT}\\assets\\marker_ev.png', 'assets'),
    (f'{WSL_PROJECT}\\assets\\everline-horizontal-logo.jpg', 'assets'),
    (f'{WSL_PROJECT}\\assets\\favicon_everline1.ico', 'assets'),
    (f'{WSL_PROJECT}\\assets\\app.html', 'assets'),
]
if os.path.exists(ICON_PATH):
    datas.append((ICON_PATH, 'assets'))

a = Analysis(
    [f'{WSL_PROJECT}\\src\\main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'pillow_heif',
        'PIL',
        'PIL.Image',
        'PIL.ExifTags',
        'webview',
        'src',
        'src.exif_extractor',
        'src.image_processor',
        'src.kmz_generator',
        'src.html_map_generator',
        'src.config',
        'src.coordinate_transform',
        'src.utils',
        'src.netlify_deployer',
        'src.marker_utils',
        'src.photo_groups',
    ],
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
    [],
    exclude_binaries=True,
    name='PicPlotterAuto',
    icon=ICON_ARG,
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

# COLLECT required for onedir mode
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PicPlotterAuto',
)
