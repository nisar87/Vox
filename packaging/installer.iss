; Inno Setup script for Vox. Installs per user, so no administrator rights are needed.
#define AppVersion GetEnv("VOX_VERSION")

[Setup]
AppId={{8C1B6B52-6C0B-4B7E-9A55-5D0C2E7A91F3}
AppName=Vox
AppVersion={#AppVersion}
AppPublisher=nisar87
AppPublisherURL=https://github.com/nisar87/Vox
DefaultDirName={localappdata}\Programs\Vox
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=VoxSetup-{#AppVersion}
SetupIconFile=vox.ico
UninstallDisplayIcon={app}\vox.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
Name: "startup"; Description: "Start Vox when I sign in to Windows"

[Files]
Source: "..\dist\Vox\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[InstallDelete]
; Left behind by 0.2.0, which was packaged differently
Type: filesandordirs; Name: "{app}\_internal"
; Replace libraries cleanly on every update
Type: filesandordirs; Name: "{app}\Lib"
Type: filesandordirs; Name: "{app}\vox"

[Icons]
Name: "{userprograms}\Vox"; Filename: "{app}\Vox.exe"; Parameters: "-m vox"; WorkingDir: "{app}"; IconFilename: "{app}\vox.ico"
Name: "{userdesktop}\Vox"; Filename: "{app}\Vox.exe"; Parameters: "-m vox"; WorkingDir: "{app}"; IconFilename: "{app}\vox.ico"; Tasks: desktopicon
Name: "{userstartup}\Vox"; Filename: "{app}\Vox.exe"; Parameters: "-m vox --no-window"; WorkingDir: "{app}"; IconFilename: "{app}\vox.ico"; Tasks: startup

[Run]
Filename: "{app}\Vox.exe"; Parameters: "-m vox"; WorkingDir: "{app}"; Description: "Start Vox"; Flags: nowait postinstall

[UninstallDelete]
; Files Python creates while running (compiled caches)
Type: filesandordirs; Name: "{app}"

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Vox.exe /F"; Flags: runhidden; RunOnceId: "StopVox"

[Code]
// Updates replace files that a running Vox holds open, so stop it first.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Vox.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);
  Result := '';
end;
