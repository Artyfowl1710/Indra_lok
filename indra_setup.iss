[Setup]
; Basic Application Information
AppName=Indra AI Sovereign Workspace
AppVersion=2.0
AppPublisher=CodersByChance
AppPublisherURL=https://github.com/
DefaultDirName={localappdata}\Indra
DefaultGroupName=Indra AI
; Output the final compiled .exe to the Desktop for easy access
OutputDir=.
OutputBaseFilename=Install_Indra_v2.0
SetupIconFile=compiler:SetupClassicIcon.ico
Compression=lzma2
SolidCompression=yes
; We do not need admin rights since we install to AppData (no permission issues)
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Files]
; Grab all files in the indra folder EXCEPT the heavy cache/venv/vault folders
Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "venv\*,SIH-26\hermes-agent\backend\venv\*,MyVault\*,models\*,*.log,*.db,*.lock,*.bak,*.git\*,__pycache__\*,SIH-26\cron\*,SIH-26\cache\*,SIH-26\logs\*,SIH-26\sessions\*,SIH-26\terminal-sessions\*,SIH-26\images\*,SIH-26\memories\*,SIH-26\audio_cache\*,SIH-26\image_cache\*,SIH-26\attachments\*,SIH-26\pastes\*"

[Icons]
; Create a Desktop shortcut pointing to start-indra.ps1
Name: "{autodesktop}\INDRA Dashboard"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoExit -File ""{app}\start-indra.ps1"""; WorkingDir: "{app}"; IconFilename: "powershell.exe"
Name: "{group}\INDRA Dashboard"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoExit -File ""{app}\start-indra.ps1"""; WorkingDir: "{app}"; IconFilename: "powershell.exe"
Name: "{group}\Uninstall Indra"; Filename: "{uninstallexe}"

[Run]
; After extraction, run the automated setup script to build environments and download models
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install-indra.ps1"""; Description: "Setting up AI Environments & Downloading Models (This may take a few minutes)..."; Flags: postinstall waituntilterminated
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoExit -File ""{app}\start-indra.ps1"""; Description: "Launch INDRA Dashboard Now"; Flags: postinstall nowait skipifsilent unchecked
