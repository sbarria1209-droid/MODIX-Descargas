[Setup]
AppId={code:ModixInstallationId}
UsePreviousLanguage=no
AppName=MODIX BIGMETER V4 - Cliente
AppVersion=11.0.0
AppVerName=MODIX BIGMETER V4 - Cliente 11
AppPublisher=MODIX Control Center
DefaultDirName={localappdata}\Programs\MODIX_8_Cliente
DefaultGroupName=MODIX 11
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
SetupIconFile=@SOURCE@\modix.ico
UninstallDisplayIcon={app}\MODIX_Cliente_11.exe
Compression=lzma2/fast
LZMANumBlockThreads=2
SolidCompression=yes
DiskSpanning=no
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes
OutputDir=@OUTPUT@
OutputBaseFilename=MODIX_Cliente_11_Instalador
VersionInfoVersion=11.0.0.0
VersionInfoDescription=Instalador MODIX 11 Cliente

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; Flags: checkedonce

[Files]
Source: "@SOURCE@\*"; DestDir: "{app}"; Excludes: "__pycache__\*,*\__pycache__\*,unins*.*,*.pyc,*.pyo,*.pdb,_obs\config\*,MODIX_*_9.exe,MODIX_*_10.exe,multicam11.json,_runtime\Lib\site-packages\imageio_ffmpeg\*,_runtime\Lib\site-packages\imageio_ffmpeg-*.dist-info\*,MODIX_*_7.exe,MODIX_*_8.exe,ABRIR_*.bat,estacion_privada.*,bridge.json,settings.json,registros\*,uploads\*,tests\*,LEEME_PRIMERO.md,VERIFICACIONES.md"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "@DOCS@\LEEME_PRIMERO.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "@DOCS@\VERIFICACIONES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MODIX Cliente 11"; Filename: "{app}\MODIX_Cliente_11.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\MODIX Cliente 11"; Filename: "{app}\MODIX_Cliente_11.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\MODIX_Cliente_11.exe"; Description: "Abrir MODIX Cliente"; Flags: nowait postinstall skipifsilent

[Code]
function ModixInstallationId(Param: String): String;
begin
  if ExpandConstant('{param:MODIX_QA|0}') = '1' then
    Result := '{C884381B-C135-41AE-82B9-16557E53D112}'
  else
    Result := '{2A7679F0-3138-41E7-985B-982B7D22F80C}';
end;
