; Studestics installer (Inno Setup 6.1 or newer, free: https://jrsoftware.org/isinfo.php)
;
; This installer does NOT contain the app. When someone runs it, it downloads
; the newest Studestics.exe from the latest GitHub release, so you compile
; this ONCE and never again (unless you change what the installer does).
;
; Every GitHub release must have a file named exactly  Studestics.exe
;
; To build: open this file in Inno Setup and press Compile (Ctrl+F9).
; The installer appears in the "installer" folder.

#define DownloadUrl "https://github.com/alyavoidx/studestics/releases/latest/download/Studestics.exe"

[Setup]
AppId={{B7C6F2A4-5D3E-4F0A-9A57-2E4C1D8E7A11}
AppName=Studestics
AppVersion=latest
AppPublisher=alyavoidx
AppPublisherURL=https://github.com/alyavoidx/studestics
DefaultDirName={autopf}\Studestics
DefaultGroupName=Studestics
DisableProgramGroupPage=yes
; Installs for the current user only, so no admin prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename=Studestics-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Studestics.exe
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; The file is downloaded into {tmp} by the [Code] below, then copied here.
Source: "{tmp}\Studestics.exe"; DestDir: "{app}"; Flags: external ignoreversion

[Icons]
Name: "{autoprograms}\Studestics"; Filename: "{app}\Studestics.exe"
Name: "{autodesktop}\Studestics"; Filename: "{app}\Studestics.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Studestics.exe"; Description: "Launch Studestics"; Flags: nowait postinstall skipifsilent

; Your data (~/.studestics) is deliberately left alone on uninstall.

[Code]
var
  DownloadPage: TDownloadWizardPage;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Downloading Studestics', 'Getting the latest version...', @OnDownloadProgress);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = wpReady then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('{#DownloadUrl}', 'Studestics.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        if DownloadPage.AbortedByUser then
          Log('Download cancelled.')
        else
          SuppressibleMsgBox(
            'Could not download Studestics. Check your internet connection and try again.' + #13#10#13#10 + GetExceptionMessage,
            mbCriticalError, MB_OK, IDOK);
        Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;
