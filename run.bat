@echo off
cd /d "%~dp0"
if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" "app.py"
) else (
    echo Chua cai dat. Chay setup.bat truoc.
    pause
)
