#define AppName "PicPlotter Auto"
#define AppExe "PicPlotterAuto.exe"
#define AppPublisher "Everline"
#define AppId "FBB44562-DC21-4172-90A2-EF1000EEC2EB"
#ifndef AppVersion
#define AppVersion "3.0.0"
#endif

[Setup]
AppId={{{#AppId}}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=no
OutputDir=..\..\dist\installer
OutputBaseFilename=PicPlotterAuto-{#AppVersion}-Setup
SetupIconFile=..\..\assets\favicon_everline1.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
VersionInfoVersion={#AppVersion}
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
