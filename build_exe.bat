@echo off
REM Builds Studestics.exe  (run this next to Studestics.py and studestics.ico)
REM Needs Python 3 on PATH. The finished file is dist\Studestics.exe

python -m pip install --upgrade pyinstaller pillow pystray google-genai
if errorlevel 1 goto :fail

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name Studestics ^
  --icon studestics.ico ^
  --add-data "studestics.ico;." ^
  --hidden-import pystray._win32 ^
  --collect-submodules google.genai ^
  --collect-data google.genai ^
  Studestics.py
if errorlevel 1 goto :fail

echo.
echo Done. Your app is dist\Studestics.exe
echo Tip: turn on Settings ^> General ^> Start with Windows from the .exe, not from the .py,
echo so Windows launches the .exe at sign-in.
pause
exit /b 0

:fail
echo.
echo Build failed - read the messages above.
pause
exit /b 1
