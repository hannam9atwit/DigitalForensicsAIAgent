# forensic_agent.spec
#
# Build with:
#   pyinstaller forensic_agent.spec
#
# Output: dist/ForensicAIAgent/ (onedir mode — faster startup, bin/ folder accessible)

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

pyside6_hidden = collect_submodules("PySide6")

# Collect all .exe and .dll files from bin/sleuthkit as binaries
# so PyInstaller copies them as executables, not data blobs.
import glob
sleuthkit_binaries = [
    (f, "bin/sleuthkit")
    for f in glob.glob("bin/sleuthkit/*")
    if os.path.isfile(f)
]

a = Analysis(
    ["gui_main.py"],
    pathex=["."],
    binaries=sleuthkit_binaries,
    datas=[
        ("assets", "assets"),
    ],
    hiddenimports=[
        *pyside6_hidden,
        "ai",
        "ai.reasoning_engine",
        "ai.rule_engine",
        "ai.anomaly_engine",
        "ai.narrative_engine",
        "ai.refinement_engine",
        "ai.report_generator",
        "core",
        "core.artifact_router",
        "core.output_normalizer",
        "core.partition_detector",
        "core.tool_runner",
        "modules.disk.mft_parser",
        "modules.disk.deleted_recovery",
        "modules.disk.timeline_builder",
        "modules.browser.history_parser",
        "modules.browser.downloads_parser",
        "modules.browser.cookies_parser",
        "modules.timeline.correlation_engine",
        "pipeline.run_pipeline",
        "gui.main_window",
        "gui.setup_wizard",
        "sqlite3",
        "csv",
        "json",
        "urllib.request",
        "urllib.error",
        "subprocess",
        "shutil",
        "platform",
        "collections",
        "re",
        "datetime",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "IPython",
        "notebook",
        "pytest",
    ],
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
    name="ForensicAIAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # keep True so errors are visible; set False once confirmed working
    icon=None,      # set to "assets/icon.ico" if you have a .ico file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ForensicAIAgent",
)
