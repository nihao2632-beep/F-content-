; 创可贴制作-内容搜索打开工具 —— Inno Setup 6 安装程序脚本（可选）
; 前提：先运行 build_exe.bat，生成 dist\创可贴制作-内容搜索打开工具.exe
; 然后：用 Inno Setup 6 打开本文件，菜单 Build -> Compile
; 产物：Output\创可贴制作-内容搜索打开工具_安装程序.exe（可安装、含开始菜单/桌面快捷方式/卸载）

#define MyAppName "创可贴制作-内容搜索打开工具"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Jiajunfeng"
#define MyAppExeName "创可贴制作-内容搜索打开工具.exe"

[Setup]
AppId={{7C4B9E51-2D8A-4C6F-9E3B-5A1F0D8C2E77}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=Output
OutputBaseFilename=创可贴制作-内容搜索打开工具_安装程序
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
