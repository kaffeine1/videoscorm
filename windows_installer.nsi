Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

!define APP_VERSION "0.3.0"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\VideoSCORM"
!ifndef STAGING
  !error "Specificare STAGING con il contenuto da installare."
!endif
!ifndef OUTPUT
  !error "Specificare OUTPUT con il percorso del Setup.exe."
!endif

Name "Video SCORM / H5P ${APP_VERSION}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\VideoSCORM"
RequestExecutionLevel user
SetCompressor /SOLID lzma
CRCCheck force
VIProductVersion "0.3.0.0"
VIAddVersionKey /LANG=1040 "ProductName" "Video SCORM"
VIAddVersionKey /LANG=1040 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1040 "FileDescription" "Installazione Video SCORM per Windows x64"
VIAddVersionKey /LANG=1040 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1040 "LegalCopyright" "Michele Dipace"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\runtime\pythonw.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS '-E -s -B $\"$INSTDIR\app\launch.pyw$\"'
!define MUI_FINISHPAGE_RUN_TEXT "Avvia Video SCORM"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Italian"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Questo pacchetto richiede Windows a 64 bit."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "Questo pacchetto richiede Windows 10 o successivo."
    Abort
  ${EndIf}
  SetShellVarContext current
  SetRegView 64
FunctionEnd

Section "Video SCORM"
  SetOutPath "$INSTDIR\runtime"
  File /r "${STAGING}/runtime/*"
  SetOutPath "$INSTDIR\app"
  File /r "${STAGING}/app/*"
  SetOutPath "$INSTDIR"
  File "${STAGING}/build-info.json"
  WriteUninstaller "$INSTDIR\Disinstalla.exe"

  DetailPrint "Verifica interfaccia e creazione di uno SCORM di prova..."
  nsExec::ExecToStack '"$INSTDIR\runtime\python.exe" -E -s -B "$INSTDIR\app\selfcheck.py"'
  Pop $0
  Pop $1
  ${If} $0 != "0"
    MessageBox MB_ICONSTOP "La prova di installazione non è riuscita. Il dettaglio è in $LOCALAPPDATA\VideoSCORM\logs\installation.log. Per ripulire i file puoi avviare $INSTDIR\Disinstalla.exe."
    SetErrorLevel 1
    Abort
  ${EndIf}

  SetOutPath "$INSTDIR\app"
  CreateDirectory "$SMPROGRAMS\Video SCORM"
  CreateShortcut "$SMPROGRAMS\Video SCORM\Video SCORM.lnk" "$INSTDIR\runtime\pythonw.exe" '-E -s -B "$INSTDIR\app\launch.pyw"'
  CreateShortcut "$DESKTOP\Video SCORM.lnk" "$INSTDIR\runtime\pythonw.exe" '-E -s -B "$INSTDIR\app\launch.pyw"'
  CreateShortcut "$SMPROGRAMS\Video SCORM\Istruzioni.lnk" "$INSTDIR\app\README-Windows.txt"
  CreateShortcut "$SMPROGRAMS\Video SCORM\Disinstalla.lnk" "$INSTDIR\Disinstalla.exe"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "Video SCORM"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "Michele Dipace"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Disinstalla.exe$\"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '$\"$INSTDIR\Disinstalla.exe$\" /S'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  SetRegView 64
  Delete "$DESKTOP\Video SCORM.lnk"
  Delete "$SMPROGRAMS\Video SCORM\Video SCORM.lnk"
  Delete "$SMPROGRAMS\Video SCORM\Istruzioni.lnk"
  Delete "$SMPROGRAMS\Video SCORM\Disinstalla.lnk"
  RMDir "$SMPROGRAMS\Video SCORM"
  RMDir /r "$INSTDIR\runtime"
  Delete "$INSTDIR\app\builder.py"
  Delete "$INSTDIR\app\batch.py"
  Delete "$INSTDIR\app\gui.py"
  Delete "$INSTDIR\app\launch.pyw"
  Delete "$INSTDIR\app\selfcheck.py"
  Delete "$INSTDIR\app\index.html"
  Delete "$INSTDIR\app\player.js"
  Delete "$INSTDIR\app\style.css"
  Delete "$INSTDIR\app\sample.mp4"
  Delete "$INSTDIR\app\README-Windows.txt"
  RMDir /r "$INSTDIR\app\h5p"
  RMDir /r "$INSTDIR\app\vendor"
  Delete "$INSTDIR\app\bin\ffprobe.exe"
  RMDir "$INSTDIR\app\bin"
  Delete "$INSTDIR\app\licenses\FFmpeg-LICENSE.txt"
  Delete "$INSTDIR\app\licenses\FFmpeg-README.txt"
  RMDir "$INSTDIR\app\licenses"
  RMDir "$INSTDIR\app"
  Delete "$INSTDIR\build-info.json"
  Delete "$INSTDIR\Disinstalla.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
SectionEnd
