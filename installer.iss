#define MyAppName "Saber Accounting"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Saber for Audit"

[Setup]
AppId={{4C848D44-EF69-47C0-86F1-5A5AA3C34E8D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Saber Accounting
DefaultGroupName=Saber Accounting
OutputDir=installer-output
OutputBaseFilename=SaberAccountingSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\SaberAccounting.exe

[Files]
Source: "dist\SaberAccounting.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\SaberAccountingServer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\Saber_for_Audit_logo.png"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Saber Accounting"; Filename: "{app}\SaberAccounting.exe"
Name: "{autodesktop}\Saber Accounting"; Filename: "{app}\SaberAccounting.exe"
Name: "{autoprograms}\Saber Accounting Shared Server"; Filename: "{app}\SaberAccountingServer.exe"

[Run]
Filename: "{app}\SaberAccounting.exe"; Description: "Open Saber Accounting"; Flags: nowait postinstall skipifsilent
