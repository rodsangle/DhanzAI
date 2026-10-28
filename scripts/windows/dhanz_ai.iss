; Inno Setup script for the DHANZ AI Windows installer.
; Build the app first (flutter build windows --release), then from the repository root:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.1.0 scripts\windows\dhanz_ai.iss
; Output: dist\dhanz-ai-<version>-windows-setup.exe

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "DHANZ AI"
#define AppExe "dhanz_ai.exe"
#define BuildDir "..\..\apps\dhanz_flutter\build\windows\x64\runner\Release"

[Setup]
; Keep AppId stable across releases so upgrades replace the previous install.
AppId={{6C1C4E2B-7D3A-4B8E-9C11-3F2D7A5B9E40}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=DHANZ AI
DefaultDirName={autopf}\DHANZ AI
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=dhanz-ai-{#AppVersion}-windows-setup
SetupIconFile=..\..\apps\dhanz_flutter\windows\runner\resources\app_icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
