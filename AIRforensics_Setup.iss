; ============================================================================
; AIRforensics_Setup.iss — Windows installer (Inno Setup 6)
;
; Build:
;   pyinstaller forensic_agent.spec
;   <download OllamaSetup.exe into redist\>  https://ollama.com/download/OllamaSetup.exe
;   ISCC AIRforensics_Setup.iss
;
; The installer bundles the app and the Ollama runtime; the language model
; downloads on first launch. That keeps the installer inside GitHub's 2 GiB
; release-asset limit, so one file ships everywhere.
; ============================================================================

#define AppName      "AIRforensics"
#define AppVersion   "1.2.0"
#define AppPublisher "AOX LLC"
#define AppExeName   "AIRforensics.exe"
#define AppId        "AIRforensics"

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
OutputBaseFilename={#AppId}_Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=assets\app.ico

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"
Name: "installollama"; Description: "Install Ollama and set up local AI (recommended)"; \
    GroupDescription: "Local AI:"

[Files]
Source: "dist\AIRforensics\*"; DestDir: "{app}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion

Source: "redist\OllamaSetup.exe"; DestDir: "{tmp}"; \
    Flags: deleteafterinstall; Tasks: installollama


[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\OllamaSetup.exe"; \
    Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"; \
    StatusMsg: "Installing Ollama (local AI runtime)..."; \
    Tasks: installollama; Flags: waituntilterminated

; Ollama's installer launches its tray app when it finishes, which pops a
; window in the middle of OUR install. Close it; the app starts the Ollama
; server itself whenever it needs one. (Ollama still auto-starts at login,
; which is its normal behavior and keeps the server warm.)
Filename: "{sys}\taskkill.exe"; \
    Parameters: "/f /im ""ollama app.exe"""; \
    Tasks: installollama; Flags: runhidden waituntilterminated skipifsilent

; Ollama's installer force-launches its own tray/chat app when it finishes
; and offers no flag to prevent it. Close it so the install stays seamless;
; AIRforensics starts the Ollama server itself whenever it needs one.
Filename: "{cmd}"; \
    Parameters: "/c timeout /t 3 /nobreak >nul & taskkill /f /im ""ollama app.exe"" >nul 2>&1"; \
    StatusMsg: "Finishing local AI setup..."; \
    Tasks: installollama; Flags: runhidden waituntilterminated

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
    DataDir := ExpandConstant('{userappdata}\AIRforensics');
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
