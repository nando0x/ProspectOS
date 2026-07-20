; Instalador do ProspectOS (Inno Setup 6)
;
; Pré-requisito: o bundle do PyInstaller já buildado em backend\dist\ProspectOS
; (rode antes: cd backend && py -m PyInstaller prospectos.spec --noconfirm)
;
; Compilar:
;   iscc instalador\prospectos.iss
; Saída: instalador\saida\ProspectOS-Setup-<versao>.exe
;
; Decisões:
; - instala por usuário (PrivilegesRequired=lowest, {autopf} => AppData\Local\Programs):
;   não pede admin, igual VSCode/Discord - e essencial pro auto-update futuro
;   conseguir trocar os arquivos sem elevação.
; - os DADOS do usuário (leads.db, backups...) ficam em %APPDATA%\ProspectOS,
;   criados pelo próprio app - o desinstalador NÃO os apaga de propósito.

#define NomeApp "ProspectOS"
#define VersaoApp "2.1.0"
#define Editor "nando0x"
#define URLApp "https://github.com/nando0x/ProspectOS"
#define ExeApp "ProspectOS.exe"

[Setup]
; GUID fixo do app - NUNCA mude entre versões (é o que faz o update substituir em vez de duplicar)
AppId={{7B3E9A52-4C1D-4E8F-9A6B-2D5C8E7F1A30}
AppName={#NomeApp}
AppVersion={#VersaoApp}
AppPublisher={#Editor}
AppPublisherURL={#URLApp}
AppSupportURL={#URLApp}/issues
DefaultDirName={autopf}\{#NomeApp}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=saida
OutputBaseFilename=ProspectOS-Setup-{#VersaoApp}
SetupIconFile=..\backend\prospectos.ico
UninstallDisplayIcon={app}\{#ExeApp}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; o bundle tem ~250MB; desabilitar o aviso de espaço baixo padrão
ExtraDiskSpaceRequired=52428800

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\backend\dist\ProspectOS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#NomeApp}"; Filename: "{app}\{#ExeApp}"
Name: "{autodesktop}\{#NomeApp}"; Filename: "{app}\{#ExeApp}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeApp}"; Description: "{cm:LaunchProgram,{#NomeApp}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; garante que o app não está rodando na desinstalação
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#ExeApp} /F"; Flags: runhidden; RunOnceId: "MatarApp"
