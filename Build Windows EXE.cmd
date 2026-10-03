@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onefile --name Any2Any --collect-all tkinterdnd2 --collect-all imageio_ffmpeg --hidden-import py7zr --hidden-import charset_normalizer --hidden-import striprtf desktop_entry.py
if errorlevel 1 exit /b 1
echo Built dist\Any2Any.exe. This single executable can be copied to any writable folder.
echo No Python installation or project files are needed to run it.
pause
