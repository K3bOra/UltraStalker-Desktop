#define MyAppName "Ultra Stalker Desktop"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Ahmed L-HadarY"
#define MyAppExeName "UltraStalkerDesktop.exe"

[Setup]
AppId={code:GetAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Ultra Stalker Desktop
DefaultGroupName=Ultra Stalker Desktop
OutputDir=..\release
OutputBaseFilename=UltraStalkerDesktop_Setup_{#MyAppVersion}_x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion=0.1.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
UsePreviousAppDir=yes
UsePreviousTasks=yes
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[InstallDelete]
; PyInstaller onedir payloads can leave obsolete DLLs/plugins after an in-place
; upgrade. Remove only generated application runtime folders/files. User data
; lives under %APPDATA%\UltraStalker and is intentionally untouched.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\mpv*"
Type: files; Name: "{app}\UltraStalkerDesktop.exe"
Type: files; Name: "{app}\PYTHON_VERSION.txt"
Type: files; Name: "{app}\BUILD_DEPENDENCIES.txt"
Type: files; Name: "{app}\MPV_PROVENANCE.json"
Type: files; Name: "{app}\RELEASE_SHA256.json"
Type: files; Name: "{app}\SELF_TEST.json"
Type: files; Name: "{app}\provenance.json"
Type: files; Name: "{app}\THIRD_PARTY_NOTICES.txt"
Type: filesandordirs; Name: "{app}\licenses"

[Files]
Source: "..\dist\UltraStalkerDesktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Ultra Stalker Desktop"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Ultra Stalker Desktop"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Ultra Stalker Desktop"; Flags: nowait postinstall skipifsilent


[Code]
function GetAppId(Param: String): String;
var
  SmokeId: String;
begin
  SmokeId := ExpandConstant('{param:SMOKETEST|}');
  if SmokeId <> '' then
    Result := '{8B1EF58E-7E5F-4D2F-9BC5-7A5D0C1E2026}-smoke-' + SmokeId
  else
    Result := '{8B1EF58E-7E5F-4D2F-9BC5-7A5D0C1E2026}';
end;
