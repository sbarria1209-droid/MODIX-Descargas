[Setup]
AppId={code:ModixInstallationId}
UsePreviousLanguage=no
AppName=MODIX BIGMETER V4 - Principal
AppVersion=11.0.0
AppVerName=MODIX BIGMETER V4 - Principal 11
AppPublisher=MODIX Control Center
DefaultDirName={localappdata}\Programs\MODIX_8_Principal
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
UninstallDisplayIcon={app}\MODIX_Principal_11.exe
Compression=lzma2/fast
LZMANumBlockThreads=2
SolidCompression=yes
DiskSpanning=no
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes
OutputDir=@OUTPUT@
OutputBaseFilename=MODIX_Principal_11_Instalador
VersionInfoVersion=11.0.0.0
VersionInfoDescription=Instalador MODIX 11 Principal

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; Flags: checkedonce

[Files]
Source: "@SOURCE@\*"; DestDir: "{app}"; Excludes: "__pycache__\*,*\__pycache__\*,unins*.*,*.pyc,*.pyo,*.pdb,_obs\config\*,MODIX_*_9.exe,MODIX_*_10.exe,multicam11.json,MODIX_*_7.exe,MODIX_*_8.exe,ABRIR_*.bat,estacion_privada.*,bridge.json,settings.json,registros\*,uploads\*,tests\*,LEEME_PRIMERO.md,VERIFICACIONES.md,station_config.py"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "@DOCS@\LEEME_PRIMERO.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "@DOCS@\VERIFICACIONES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "@DOCS@\station_config.py"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MODIX Principal 11"; Filename: "{app}\MODIX_Principal_11.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\MODIX Principal 11"; Filename: "{app}\MODIX_Principal_11.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\MODIX_Principal_11.exe"; Description: "Abrir MODIX Principal"; Flags: nowait postinstall skipifsilent

[Code]
function ModixInstallationId(Param: String): String;
begin
  if ExpandConstant('{param:MODIX_QA|0}') = '1' then
    Result := '{C884381B-C135-41AE-82B9-16557E53D111}'
  else
    Result := '{6B2DA679-A4D7-4DF1-9892-1255EF452341}';
end;
