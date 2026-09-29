#ifndef MyAppVersion
  #define MyAppVersion "2.7.1"
#endif
#ifndef VcRedistPath
  #define VcRedistPath "..\build\prerequisites\VC_redist.x64.exe"
#endif

#define MyAppName "MKT"
#define MyAppPublisher "S e M"
#define MyAppExeName "MKT.exe"

[Setup]
AppId={{A3BF4456-03D9-4C87-9EB2-466C27E38D67}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\MKT
DefaultGroupName=MKT
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=MKT_Setup_{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Instalador do MKT
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\release\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\release\MKTUpdater.exe"; DestDir: "{localappdata}\AlbionMKT\updater"; Flags: ignoreversion
Source: "{#VcRedistPath}"; DestDir: "{tmp}"; DestName: "VC_redist.x64.exe"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\MKT"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\MKT"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{tmp}\VC_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Instalando componentes oficiais do Microsoft Visual C++..."; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o MKT"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{localappdata}\AlbionMKT\bot_control.json"
Type: files; Name: "{localappdata}\AlbionMKT\update-status.json"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := IsWin64;
  if not Result then
    MsgBox('O MKT requer Windows 10 ou 11 de 64 bits.', mbError, MB_OK);
end;
