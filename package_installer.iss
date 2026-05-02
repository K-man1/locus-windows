#define MyAppName "Locus"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "K-man1"
#define MyAppURL "https://locusfocusapp.netlify.app"
#define MyAppExeName "Locus.exe"

[Setup]
AppId={{E3A1B2C4-7F8D-4E9A-B123-456789ABCDEF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=LocusSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Run at startup via registry, not a shortcut, so it launches silently
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "runonstartup"; Description: "Launch Locus when Windows starts"; GroupDescription: "Startup:"; Flags: checked

[Files]
; Main executables built by PyInstaller
Source: "dist\Locus.exe";  DestDir: "{app}"; Flags: ignoreversion
Source: "dist\locusd.exe"; DestDir: "{app}"; Flags: ignoreversion
; Example config — only copied if no config exists yet (handled in [Code])
Source: "config.example.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; Add to startup only if the user checked the task
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Locus"; \
  ValueData: """{app}\{#MyAppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: runonstartup

[Run]
; Copy default config to %APPDATA%\Locus if none exists yet (done in [Code])
; Launch Locus immediately after install (no separate checkbox — it's silent)
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Locus now"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Kill running instances before uninstall
Filename: "taskkill"; Parameters: "/F /IM Locus.exe";  Flags: runhidden
Filename: "taskkill"; Parameters: "/F /IM locusd.exe"; Flags: runhidden

[Code]
var
  ConfigDir: string;
  ConfigPath: string;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExampleConfig: string;
begin
  if CurStep = ssPostInstall then
  begin
    // Create %APPDATA%\Locus if it doesn't exist
    ConfigDir := ExpandConstant('{userappdata}\Locus');
    ConfigPath := ConfigDir + '\config.json';
    ExampleConfig := ExpandConstant('{app}\config.example.json');

    if not DirExists(ConfigDir) then
      CreateDir(ConfigDir);

    // Only copy example config if the user doesn't already have one
    if not FileExists(ConfigPath) then
      FileCopy(ExampleConfig, ConfigPath, False);
  end;
end;
