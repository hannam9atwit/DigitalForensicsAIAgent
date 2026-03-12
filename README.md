# Forensic AI Agent

A cross-platform digital forensics investigation tool powered by a local LLM (Llama 3.2 via Ollama), with optional Anthropic Claude API support.

---

## For End Users (Running the App)

### Windows
1. Download and unzip `ForensicAIAgent-windows.zip`
2. Run `ForensicAIAgent.exe`
3. On first launch, a setup wizard will install Ollama and download the AI model (~2 GB). You only need internet for this step.
4. After setup, the app works fully offline.

### Linux
1. Download `ForensicAIAgent.AppImage`
2. Make it executable and run it:
   ```bash
   chmod +x ForensicAIAgent.AppImage
   ./ForensicAIAgent.AppImage
   ```
3. The setup wizard handles Ollama installation on first launch.

> **Skip AI setup?** You can click "Skip" in the wizard. The app will still analyse artifacts and produce reports — it just uses rule-based narrative text instead of an LLM.

---

## For Developers (Building from Source)

### Prerequisites

- Python 3.11+
- Git
- The SleuthKit Windows binaries in `bin/sleuthkit/` (not included in repo — see below)

```bash
git clone https://github.com/yourorg/forensic-ai-agent.git
cd forensic-ai-agent
pip install -r requirements.txt
python gui_main.py
```

### SleuthKit Binaries

Place the SleuthKit `.exe` files (Windows) or binaries (Linux) into:
```
bin/
└── sleuthkit/
    ├── fls.exe
    ├── mmls.exe
    ├── icat.exe
    └── ...
```

Download from: https://www.sleuthkit.org/sleuthkit/download.php

### requirements.txt

```
PySide6>=6.6.0
pyinstaller>=6.0
```

No additional AI/ML dependencies — Ollama runs as a separate system process.

---

## Building Distributable Packages

### Windows (run on a Windows machine)

```bat
build_windows.bat
```

Output: `dist\ForensicAIAgent\` — zip this folder for distribution.

### Linux (run on Ubuntu 22.04+)

```bash
chmod +x build_linux.sh
./build_linux.sh
```

Output:
- `dist/ForensicAIAgent/` — portable folder
- `dist/ForensicAIAgent.AppImage` — single-file distributable

---

## AI Configuration

### Default: Local LLM (Ollama)
- Model: `llama3.2:3b` (~2 GB download)
- Runs entirely offline after first setup
- No API key required

### Optional Upgrade: Anthropic Claude API
If you have an Anthropic API key, go to **Tools → Settings** and enter it.
Claude will be used instead of the local model when available, with Ollama as fallback.

Priority order: **Ollama → Claude API → Rule-based fallback**

---

## Project Structure

```
forensic-ai-agent/
├── ai/
│   ├── anomaly_engine.py       # Heuristic anomaly detection
│   ├── narrative_engine.py     # Builds structured forensic narrative
│   ├── reasoning_engine.py     # Orchestrates rule + anomaly engines
│   ├── refinement_engine.py    # LLM integration (Ollama / Claude)
│   ├── report_generator.py     # Markdown report output
│   └── rule_engine.py          # Deterministic DFIR rules
├── core/
│   ├── artifact_router.py      # Detects artifact type
│   ├── output_normalizer.py    # Normalises SleuthKit output
│   ├── partition_detector.py   # NTFS offset detection via mmls
│   └── tool_runner.py          # Runs bundled SleuthKit binaries
├── modules/
│   ├── browser/                # Chrome history / downloads / cookies
│   ├── disk/                   # MFT parser, deleted recovery, timeline
│   └── timeline/               # Unified timeline correlation
├── gui/
│   ├── main_window.py          # PySide6 main window
│   └── setup_wizard.py         # First-run Ollama install wizard
├── pipeline/
│   └── run_pipeline.py         # End-to-end pipeline orchestration
├── bin/sleuthkit/              # SleuthKit binaries (not in repo)
├── assets/                     # Icons and splash screen
├── gui_main.py                 # Application entry point
├── forensic_agent.spec         # PyInstaller build spec
├── build_windows.bat           # Windows build script
└── build_linux.sh              # Linux build + AppImage script
```

---

## Roadmap

- [ ] IOC (Indicator of Compromise) rule layer
- [ ] Firefox / Edge browser support
- [ ] SHA-256 hashing for chain of custody
- [ ] Browser DB extraction from within disk images
- [ ] Windows installer (Inno Setup) with optional AI toggle