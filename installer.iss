; installer.iss
; Inno Setup script for SSH Console Launcher.
; Bump AppVersion (and re-tag/re-release) for future versions.
;
; Build sequence:
;   1. powershell -File build_exe.ps1      -> produces dist\SSH_Console_Launcher.exe
;   2. ISCC.exe installer.iss              -> produces installer_output\SSH-Console-Launcher-Setup-<version>.exe
;
; plink.exe and pscp.exe must both be present in this folder before compiling
; (see README.md / doc/BUILD.md) - they ship as loose sibling files next to
; the installed exe, not bundled inside it (see the note in build_exe.ps1 for
; why plink.exe works this way; pscp.exe follows the same pattern).

#define MyAppName "SSH Console Launcher"
#define MyAppVersion "1.5.10"
#define MyAppPublisher "Ricardo Velez"
#define MyAppURL "https://github.com/Trukitro/SSH-Console-Launcher"
#define MyAppExeName "SSH_Console_Launcher.exe"

[Setup]
AppId={{B1A5B220-B7F2-433D-B412-F9BCBB2BE6B7}
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
LicenseFile=LICENSE
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
OutputDir=installer_output
OutputBaseFilename=SSH-Console-Launcher-Setup-v{#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\SSH_Console_Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "plink.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "pscp.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "VERSION_HISTORY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "FEATURES_PLAN.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
