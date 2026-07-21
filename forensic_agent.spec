# forensic_agent.spec
#
# Build with:
#   pyinstaller forensic_agent.spec
#
# Output: dist/AIRforensics/ (onedir mode — faster startup, bin/ folder accessible)

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
    ["gui_main_native.py"],
    pathex=["."],
    binaries=sleuthkit_binaries,
    datas=[
        ("assets", "assets"),
        ("formats", "formats"),
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
        "ai.format_library",
        "ai.surface_engine",
        "core",
        "core.artifact_router",
        "core.output_normalizer",
        "core.partition_detector",
        "core.tool_runner",
        "core.ollama_runtime",
        "modules.disk.mft_parser",
        "modules.disk.deleted_recovery",
        "modules.disk.timeline_builder",
        "modules.browser.history_parser",
        "modules.browser.downloads_parser",
        "modules.browser.cookies_parser",
        "modules.timeline.correlation_engine",
        "modules.network.pcap_parser",
        "pipeline.run_pipeline",
        "gui_v2",
        "gui_v2.main_window",
        "gui_v2.setup_wizard",
        "gui_v2.ai_worker",
        "gui_v2.app_settings",
        "gui_v2.case_store",
        "gui_v2.case_model",
        "gui_v2.content",
        "gui_v2.data_adapter",
        "gui_v2.interpreter",
        "gui_v2.pipeline_router",
        "gui_v2.report_pdf",
        "gui_v2.evidence_export",
        "gui_v2.case_history",
        "gui_v2.intake_dialog",
        "gui_v2.theme",
        "gui_v2.widgets",
        "gui_v2.sidebar",
        "gui_v2.rail",
        "gui_v2.screens",
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
    name="AIRforensics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="assets/app.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AIRforensics",
)
