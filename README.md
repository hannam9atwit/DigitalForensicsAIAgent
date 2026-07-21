# AIRforensics

> **Note:** the product name is still being finalized. To rebrand, change
> `AppName` in `AIRforensics_Setup.iss` and `setApplicationName` in
> `gui_main_native.py`.

A digital forensics investigation console powered by a local LLM (Ollama),
with optional Anthropic Claude API support. Evidence never leaves the machine.

---

## Install (Windows)

1. Download and run **`AIRforensics_Setup.exe`**. No admin rights needed — it
   installs per-user.
2. Keep **"Install Ollama and set up local AI"** checked (recommended).
3. Launch the app. It finishes the one-time model download (~2 GB) on first run.

Every install starts completely fresh: no cases, no history, no prior data.
A **Demo Case** is available from `Case ▸ Open Demo Case` to explore the
interface — it is clearly-labeled fixture data, never real evidence.

If local AI setup was skipped, the app runs in rule-based mode; enable AI
any time from **Settings ▸ Run local AI setup**.

## AI engines

The default engine is **Ollama running locally** — it writes the case
overview, the "in plain terms" explanations, the per-artifact "what it means"
notes, and the full investigation report, entirely on your machine. In
Settings you can switch the engine to the Anthropic API (bring your own key —
held in memory only, never written to disk) or to rule-based text with no AI.

Output formats live in `formats/` — one spec file per surface (report
sections, case overview, plain terms, what it means). The AI is validated
against these specs at generation time; updating a spec file changes the AI's
output format with no code changes.

---

## Building from source

### Prerequisites
- Python 3.11+, `pip install -r requirements.txt`
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) — installers
- [Ollama](https://ollama.com) on the build machine — Full installer only
- SleuthKit Windows binaries in `bin/sleuthkit/`
  ([download](https://www.sleuthkit.org/sleuthkit/download.php))

### Run from source
```bash
pip install -r requirements.txt
python gui_main_native.py
```

### Build the installers
```bat
build_windows.bat
```
The script runs PyInstaller, downloads `OllamaSetup.exe`, and compiles
`dist/AIRforensics_Setup.exe`.

### Linux
`build_linux.sh` produces the AppImage; the in-app setup wizard handles
Ollama on first launch.

---

## Distributing

- **GitHub Releases:** upload `AIRforensics_Setup.exe` as the release asset. It stays
  under GitHub's 2 GiB per-file limit because the language model downloads on
  first launch rather than being bundled.

## Project layout

```
gui_main_native.py     entry point (first-run AI check → main window)
gui_v2/                the application UI (screens, rail, theme, wizard)
ai/                    narrative + surface engines, format library
formats/               AI output format specs (edit these, not code)
core/                  ollama_runtime, SleuthKit tool runners, parsers
modules/, pipeline/    artifact parsers (disk, browser, network) and the pipeline
tools/                 build and maintenance tooling
AIRforensics_Setup.iss   Windows installer
```
