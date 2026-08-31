#define MyAppName "ResumeBranch"
#define MyAppVersion "1.1.1"
#define MyAppPublisher "ResumeBranch"
#define MyAppExeName "ResumeBranch.exe"

#ifndef SourceDir
  #error SourceDir must be supplied by the packaging script.
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by the packaging script.
#endif
#ifndef SetupIcon
  #error SetupIcon must be supplied by the packaging script.
#endif
#ifndef LanguageFile
  #error LanguageFile must be supplied by the packaging script.
#endif

[Setup]
AppId={{0D284EDA-A912-4B22-86B9-E3D06A43D4E7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=ResumeBranch-Setup-x64
SetupIconFile={#SetupIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=no
UsePreviousTasks=no
VersionInfoVersion=1.1.1.0
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} 本地版安装程序
VersionInfoCompany={#MyAppPublisher}

[Languages]
Name: "chinesesimp"; MessagesFile: "{#LanguageFile}"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\app\data"
Name: "{app}\app\data\source_documents"
Name: "{app}\app\output\resumes"
Name: "{app}\app\.local-run"

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--stop"; Flags: runhidden waituntilterminated skipifdoesntexist

[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\resources"
Type: filesandordirs; Name: "{app}\licenses"
