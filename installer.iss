; installer.iss - Inno Setup script for SSH Console Launcher v2.
;
; Build sequence:
;   1. powershell -File build_exe.ps1      -> produces dist\SSH_Console_Launcher_v2.exe
;   2. ISCC.exe installer.iss              -> produces installer_output\SSH-Console-Launcher-v2-Setup-<version>.exe
;
; Unlike v1, there is nothing else to bundle - v2 has zero external binary
; dependencies (paramiko talks SSH directly; the terminal is xterm.js running
; inside the OS's own WebView2 runtime, which Windows 11 already ships with).

#define MyAppName "SSH Console Launcher v2"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "Rikion"
#define MyAppURL "https://github.com/Trukitro/SSH-Console-Launcher"
#define MyAppExeName "SSH_Console_Launcher_v2.exe"

[Setup]
AppId={{E3B6B6E2-8B1B-4E33-9C0A-2E8C7B9F4A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=image\app_icon.ico
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
OutputDir=installer_output
OutputBaseFilename=SSH-Console-Launcher-v2-Setup-v{#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\SSH_Console_Launcher_v2.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
