[Setup]
AppName=CLEON ERP
AppVersion=3.0.0
DefaultDirName={localappdata}\Programs\CLEON ERP
DefaultGroupName=CLEON ERP
PrivilegesRequired=lowest
OutputDir=C:\Users\ammar\FuelStationERP_V2\installer_output
OutputBaseFilename=CLEON_ERP_Setup
WizardStyle=modern

[Files]
Source: "C:\Users\ammar\FuelStationERP_V2\Version3\dist\CLEON_ERP\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C:\Users\ammar\FuelStationERP_V2\Version3\fuel_station.db"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{autoprograms}\CLEON ERP"; Filename: "{app}\CLEON_ERP.exe"; WorkingDir: "{app}"