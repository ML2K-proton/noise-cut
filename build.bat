@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo Chay setup.bat truoc.
    pause
    exit /b 1
)
if not exist "assets\icon.ico" (
    echo Thieu assets\icon.ico
    pause
    exit /b 1
)
"venv\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller

echo [1/2] Build 1 file (de chia se, khoi dong cham hon)...
"venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name noise-cut ^
    --icon "assets\icon.ico" ^
    --add-data "noisecut\rnnoise.dll;noisecut" ^
    --add-data "noisecut\vendor\VBCABLE_NOTICE.txt;noisecut\vendor" ^
    --add-data "assets\icon.ico;assets" ^
    --add-data "LICENSE;." ^
    --add-data "THIRD_PARTY_NOTICES.md;." ^
    --hidden-import pystray._win32 ^
    --hidden-import pynput.keyboard._win32 ^
    --hidden-import pynput.mouse._win32 ^
    --hidden-import pynput._util.win32 ^
    --collect-all deepfilternet_rs ^
    --distpath dist app.py

echo [2/2] Build 1 thu muc (khoi dong nhanh, dung hang ngay)...
"venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --name noise-cut ^
    --icon "assets\icon.ico" ^
    --add-data "noisecut\rnnoise.dll;noisecut" ^
    --add-data "noisecut\vendor\VBCABLE_NOTICE.txt;noisecut\vendor" ^
    --add-data "assets\icon.ico;assets" ^
    --add-data "LICENSE;." ^
    --add-data "THIRD_PARTY_NOTICES.md;." ^
    --hidden-import pystray._win32 ^
    --hidden-import pynput.keyboard._win32 ^
    --hidden-import pynput.mouse._win32 ^
    --hidden-import pynput._util.win32 ^
    --collect-all deepfilternet_rs ^
    --distpath dist-folder app.py

echo.
copy /y LICENSE dist\ >nul
copy /y THIRD_PARTY_NOTICES.md dist\ >nul
copy /y LICENSE dist-folder\noise-cut\ >nul
copy /y THIRD_PARTY_NOTICES.md dist-folder\noise-cut\ >nul
if exist "dist\noise-cut.exe" echo OK: dist\noise-cut.exe
if exist "dist-folder\noise-cut\noise-cut.exe" echo OK: dist-folder\noise-cut\noise-cut.exe
pause


