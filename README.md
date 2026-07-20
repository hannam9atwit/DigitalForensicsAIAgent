# Forensic AI Agent

> **Note:** the product name is still being finalized. To rebrand, change
> `AppName` in `ForensicAIAgent_Setup.iss` and `setApplicationName` in
> `gui_main_native.py`.

A digital forensics investigation console powered by a local LLM (Ollama),
with optional Anthropic Claude API support. Evidence never leaves the machine.

---

## Install (Windows)

Two installers, same app:

| Installer | Size | Best for |
|---|---|---|
| **Setup-Full.exe** | ~2.4 GB | Fully offline install — Ollama and the AI model are bundled. Works with no internet, ever. |
| **Setup-Lite.exe** | ~500 MB | Smaller download — the AI model (~2 GB) downloads automatically on first launch. |

1. Run the installer. No admin rights needed — it installs per-user.
2. Keep **"Install Ollama and set up local AI"** checked (recommended).
3. Launch the app. Full installs are ready immediately; Lite installs finish
   the one-time model download on first run.

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
ollama pull llama3.2:3b     &:: once, for the Full variant
build_windows.bat
```
The script runs PyInstaller, downloads `OllamaSetup.exe`, stages the model
payload (`tools/prepare_model_payload.py`), and compiles both installers into
`dist/`.

### Linux
`build_linux.sh` produces the AppImage; the in-app setup wizard handles
Ollama on first launch.

---

## Distributing

- **GitHub Releases:** upload `Setup-Lite.exe`. (The Full installer exceeds
  GitHub's 2 GiB per-file release limit — don't upload it there.)
- **Website:** host `Setup-Full.exe` as the primary download and link the
  Lite installer as the "smaller download" alternative. Serve it from object
  storage or a CDN rather than shared hosting — a 2.4 GB file will saturate a
  small web server's bandwidth quickly.

## Project layout

```
gui_main_native.py     entry point (first-run AI check → main window)
gui_v2/                the application UI (screens, rail, theme, wizard)
ai/                    narrative + surface engines, format library
formats/               AI output format specs (edit these, not code)
core/                  ollama_runtime, SleuthKit tool runners, parsers
modules/, pipeline/    artifact parsers and the analysis pipeline
tools/                 build tooling (model payload staging)
ForensicAIAgent_Setup.iss   Windows installer (Full + Lite variants)
```
