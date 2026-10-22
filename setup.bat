@echo off
cd /d "%~dp0"

set "PYEXE="
for %%D in (
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%ProgramFiles%\Python312\python.exe"
  "%ProgramFiles%\Python311\python.exe"
) do if not defined PYEXE if exist %%D set "PYEXE=%%~fD"

if not defined PYEXE (
  for /f "usebackq delims=" %%P in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%P"
)
if not defined PYEXE (
  python -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE (
  echo Khong tim thay Python 3.
  echo Tai Python 3.12 tai https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo Dang tao moi truong Python...
  "%PYEXE%" -m venv venv
)
if not exist "venv\Scripts\python.exe" (
  echo Khong tao duoc venv.
  pause
  exit /b 1
)

"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Cai dat xong.
echo - Chay run.bat de mo ung dung.
echo - Chay build.bat de dong goi .exe.
pause
