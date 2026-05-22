# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ExamSentinel — single-file windowed exe.

Build:  pyinstaller --clean ExamSentinel.spec
Output: client/build/dist/ExamSentinel.exe
"""

import os
import sys

# Paths ------------------------------------------------------------------
# SPECPATH is set by PyInstaller to the directory containing the spec file.
SPEC_DIR = SPECPATH                                           # client/build/
CLIENT_DIR = os.path.normpath(os.path.join(SPEC_DIR, ".."))  # client/
PROJECT_ROOT = os.path.normpath(os.path.join(CLIENT_DIR, ".."))  # ExamSentinel/

ENTRY = os.path.join(CLIENT_DIR, "app", "main.py")
ICON = os.path.join(SPEC_DIR, "icon.ico")
MANIFEST = os.path.join(SPEC_DIR, "examsentinel.manifest")

# Hidden imports ----------------------------------------------------------
# PyInstaller misses these dynamic / C-extension imports.
HIDDEN = [
    # pywin32
    "win32api", "win32con", "win32gui", "win32process",
    "win32clipboard", "win32event", "win32ui", "pywintypes",
    "win32com", "win32com.client", "pythoncom",
    # WMI
    "wmi", "win32com", "win32com.client",
    # psutil internals (C extension often missed)
    "psutil", "psutil._psutil_windows",
    # screeninfo
    "screeninfo", "screeninfo.enumerators", "screeninfo.enumerators.windows",
    # requests internals sometimes missed
    "requests", "charset_normalizer", "certifi", "urllib3",
    "idna", "idna.core",
    # tkinter (explicit)
    "tkinter", "tkinter.ttk", "tkinter.messagebox",
    "tkinter.filedialog", "tkinter.scrolledtext",
    # dotenv
    "dotenv",
    # Pillow (if used at runtime for icon gen — not needed but safe)
    # stdlib often needed
    "ctypes", "ctypes.wintypes",
    "threading", "json", "logging",
]

# Data files --------------------------------------------------------------
# (source, dest_in_bundle)
DATAS = [
    (os.path.join(SPEC_DIR, "icon.ico"), "build"),
    (os.path.join(SPEC_DIR, "examsentinel.manifest"), "build"),
]

# Add .env if it exists (runtime config)
_env_file = os.path.join(CLIENT_DIR, ".env")
if os.path.isfile(_env_file):
    DATAS.append((_env_file, "."))

# Analysis ----------------------------------------------------------------
a = Analysis(
    [ENTRY],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "scipy", "pandas", "IPython", "notebook"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ExamSentinel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # windowed mode — no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON],
    manifest=MANIFEST,
    uac_admin=True,       # triggers requireAdministrator in the manifest
)
