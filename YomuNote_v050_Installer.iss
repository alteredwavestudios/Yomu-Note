; Yomu Note v0.8.2 Windows installer (Inno Setup 6 or 7)
; Place this file next to main.py and build-windows.ps1 in the extracted
; Yomu Note v0.8.2 source folder. First build the app with build-windows.ps1.
;
; IMPORTANT: Keep AppId unchanged for future Yomu Note updates, so Windows
; recognises subsequent installers as upgrades to the same application.

#define MyAppName "Yomu Note"
#define MyAppVersion "0.8.2"
#define MyAppExeName "Yomu Note.exe"

[Setup]
AppId={{974AD665-3F47-4CC5-9AAE-0A5F43565469}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion=0.8.2.0
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Yomu Note
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=installer
OutputBaseFilename=YomuNote_Setup_v0.8.2
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern
Compression=lzma
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Include every PyInstaller onedir file, including the _internal folder.
; These files are private to Yomu Note, so ignoreversion is appropriate.
; OCR runtime is included recursively from _internal\ocr. Do not remove it.
Source: "dist\Yomu Note\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
