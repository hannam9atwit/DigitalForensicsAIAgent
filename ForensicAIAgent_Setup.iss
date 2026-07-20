; ============================================================================
; ForensicAIAgent_Setup.iss — Windows installer (Inno Setup 6)
;
; Product name is TBD: change AppName below (and nothing else) when the final
; name lands. Everything — folders, shortcuts, uninstall entry — follows it.
;
; Two variants build from this one script:
;   FULL (default)         — bundles OllamaSetup.exe AND the model blobs.
;                            ~2.4 GB, installs fully offline. Host on the
;                            website (exceeds GitHub's 2 GiB release limit).
;   LITE (/DLITE on ISCC)  — bundles only OllamaSetup.exe; the app pulls the
;                            model on first launch. ~500 MB, fits GitHub
;                            Releases.
;
; Design decisions worth knowing:
;   * PER-USER install (PrivilegesRequired=lowest). Ollama's own installer is
;     per-user; if this installer ran elevated, Ollama would install for the
;     admin account instead of the person using the app, and the model blobs
;     would land in the wrong profile's ~/.ollama. Per-user also means no UAC
;     prompt at all.
;   * Ollama's installer is Inno Setup too, so /VERYSILENT is its silent flag.
;   * Model blobs copy into {%USERPROFILE}\.ollama\models — the layout
;     tools/prepare_model_payload.py stages. Ollama discovers them with no
;     pull and no network.
;
; Build:
;   pyinstaller forensic_agent.spec
;   ollama pull llama3.2:3b                       (Full only, build machine)
;   python tools\prepare_model_payload.py         (Full only)
;   <download OllamaSetup.exe into redist\>       https://ollama.com/download/OllamaSetup.exe
;   ISCC ForensicAIAgent_Setup.iss                (Full)
;   ISCC /DLITE ForensicAIAgent_Setup.iss         (Lite)
; ============================================================================

#define AppName      "Forensic AI Agent"
#define AppVersion   "1.0.0"
#define AppPublisher "AOX LLC"
#define AppExeName   "ForensicAIAgent.exe"
#define AppId        "ForensicAIAgent"

#ifdef LITE
  #define VariantSuffix "-Lite"
#else
  #define VariantSuffix "-Full"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppId}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename={#AppId}_Setup{#VariantSuffix}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=assets\app.ico
; The model blobs are already compressed; recompressing 2 GB gains almost
; nothing and multiplies build time. lzma2/max still applies to the app files.

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"
Name: "installollama"; Description: "Install Ollama and set up local AI (recommended)"; \
    GroupDescription: "Local AI:"

[Files]
Source: "dist\ForensicAIAgent\*"; DestDir: "{app}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion

Source: "redist\OllamaSetup.exe"; DestDir: "{tmp}"; \
    Flags: deleteafterinstall; Tasks: installollama

#ifndef LITE
Source: "redist\ollama-models\*"; DestDir: "{%USERPROFILE}\.ollama\models"; \
    Flags: recursesubdirs createallsubdirs uninsneveruninstall; Tasks: installollama
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\OllamaSetup.exe"; \
    Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"; \
    StatusMsg: "Installing Ollama (local AI runtime)..."; \
    Tasks: installollama; Flags: waituntilterminated

Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The app's own install folder only. Case data and the model are handled in
; code below so the user gets a choice instead of silent deletion.
Type: filesandordirs; Name: "{app}"

[Code]
{ On uninstall, offer — never force — removal of case data. Evidence analysis
  results may be the only copy of an examiner's work product. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\ForensicAIAgent');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete saved cases and app settings?' + #13#10 +
                DataDir + #13#10#13#10 +
                'Choose No to keep them for a future reinstall.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
