@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" -X utf8 "%~dp0terminal_gui.py"
  exit /b
)
where pyw.exe >nul 2>nul
if not errorlevel 1 (
  start "" pyw.exe -3 "%~dp0terminal_gui.py"
  exit /b
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
  start "" pythonw.exe -X utf8 "%~dp0terminal_gui.py"
  exit /b
)
if exist "%USERPROFILE%\.unsloth\studio\unsloth_studio\Scripts\pythonw.exe" (
  start "" "%USERPROFILE%\.unsloth\studio\unsloth_studio\Scripts\pythonw.exe" -X utf8 "%~dp0terminal_gui.py"
  exit /b
)
echo Install Python 3.11 or newer with Tk, then run this launcher again.
echo You can also run: python terminal_gui.py
pause
exit /b 1
