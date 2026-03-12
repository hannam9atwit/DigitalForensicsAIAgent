# forensic_agent.spec
#
# Build with:
#   pyinstaller forensic_agent.spec
#
# Output:  dist/ForensicAIAgent/  (folder) or dist/ForensicAIAgent.exe (onefile)
# We use onedir (not onefile) so startup is fast and the bin/ folder is accessible.

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all submodules for PySide6 (avoids missing plugin errors)
pyside6_hidden = collect_submodules("PySide6")

a = Analysis(
    ["gui_main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # Bundle the SleuthKit binaries
        ("bin/sleuthkit", "bin/sleuthkit"),
        # Bundle splash / asset images
        ("assets",        "assets"),
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
        # Strip things we definitely don't use to keep size down
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
    exclude_binaries=True,    # onedir mode — faster startup
    name="ForensicAIAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                 # compress with UPX if available
    console=False,            # no console window on Windows
    icon="assets/icon.ico",   # replace with your icon path
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
