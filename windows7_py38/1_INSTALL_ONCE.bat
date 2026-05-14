@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Krisha Bot - Install Once

set "PYTHONIOENCODING=utf-8:backslashreplace"
set "PYTHONUTF8=1"
set PIP_DISABLE_PIP_VERSION_CHECK=1
set "PF86=%ProgramFiles(x86)%"
set "PYTHON_INSTALLER=python-3.8.10-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe"
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" if not defined PROCESSOR_ARCHITEW6432 (
    set "PYTHON_INSTALLER=python-3.8.10.exe"
    set "PYTHON_URL=https://www.python.org/ftp/python/3.8.10/python-3.8.10.exe"
)
set "CHROMEDRIVER_VERSION=109.0.5414.74"
set "CHROMEDRIVER_ZIP=chromedriver_109_win32.zip"
set "CHROMEDRIVER_URL=https://chromedriver.storage.googleapis.com/109.0.5414.74/chromedriver_win32.zip"

echo.
echo  =========================================
echo   Krisha Bot - one-time install
echo  =========================================
echo.

call :find_python38
if not defined BOOTSTRAP_PY (
    echo  Python 3.8.x was not found. Installing Python 3.8.10...
    call :install_python38
    if errorlevel 1 goto :fail
    call :find_python38
)

if not defined BOOTSTRAP_PY (
    echo  [ERROR] Python 3.8.10 install finished, but Python 3.8 still was not found.
    echo  Restart this window or install Python 3.8.10 manually with "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('%BOOTSTRAP_PY% --version 2^>^&1') do set PY_VER=%%v
echo  Python %PY_VER% found.

set CREATED_ENV=0
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        set CREATED_ENV=1
        echo  Created .env from .env.example.
    ) else (
        echo  [ERROR] .env.example was not found.
        echo.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  Creating virtual environment...
    %BOOTSTRAP_PY% -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Could not create virtual environment.
        echo.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\pip.exe" (
    echo  [ERROR] pip was not found in .venv.
    echo.
    pause
    exit /b 1
)

echo.
echo  Installing/updating Python packages...
.venv\Scripts\python -m pip --disable-pip-version-check install --upgrade "pip<25" "setuptools<76" wheel
if errorlevel 1 (
    echo  [ERROR] Could not upgrade pip tooling.
    echo.
    pause
    exit /b 1
)

.venv\Scripts\pip --disable-pip-version-check install -r requirements.txt
if errorlevel 1 (
    echo  [ERROR] Dependency installation failed.
    echo.
    pause
    exit /b 1
)

echo. > .venv\.deps_installed

.venv\Scripts\python -c "import selenium, requests, bs4, dotenv; print(' Runtime imports OK')"
if errorlevel 1 (
    echo  [ERROR] Runtime import check failed.
    echo.
    pause
    exit /b 1
)

call :ensure_chromedriver
if errorlevel 1 goto :fail

call :check_chrome

echo.
if "%CREATED_ENV%"=="1" (
    echo  .env was created. Fill it now, save, then run 2_RUN_BOT.bat.
    echo.
    start notepad ".env"
) else (
    echo  .env already exists. Check it if credentials changed.
)

echo.
echo  Install finished.
echo  Next time use: 2_RUN_BOT.bat
echo.
pause
exit /b 0

:find_python38
set "BOOTSTRAP_PY="
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "BOOTSTRAP_PY=.venv\Scripts\python.exe"
        goto :eof
    )
)

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "BOOTSTRAP_PY=python"
    goto :eof
)

py -3.8 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "BOOTSTRAP_PY=py -3.8"
    goto :eof
)

if exist "%LOCALAPPDATA%\Programs\Python\Python38\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python38\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "BOOTSTRAP_PY="%LOCALAPPDATA%\Programs\Python\Python38\python.exe""
        goto :eof
    )
)
if exist "%ProgramFiles%\Python38\python.exe" (
    "%ProgramFiles%\Python38\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "BOOTSTRAP_PY="%ProgramFiles%\Python38\python.exe""
        goto :eof
    )
)
if defined PF86 if exist "!PF86!\Python38-32\python.exe" (
    "!PF86!\Python38-32\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "BOOTSTRAP_PY="!PF86!\Python38-32\python.exe""
        goto :eof
    )
)
if defined PF86 if exist "!PF86!\Python38\python.exe" (
    "!PF86!\Python38\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "BOOTSTRAP_PY="!PF86!\Python38\python.exe""
        goto :eof
    )
)
goto :eof

:install_python38
if not exist "%PYTHON_INSTALLER%" (
    echo  Downloading Python 3.8.10...
    call :download_file "%PYTHON_URL%" "%PYTHON_INSTALLER%"
    if errorlevel 1 (
        echo  [ERROR] Could not download Python installer.
        echo  Download manually: %PYTHON_URL%
        echo.
        pause
        exit /b 1
    )
)

echo  Running Python installer...
start /wait "" "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0 Include_doc=0
if errorlevel 1 (
    echo  [ERROR] Python installer failed.
    echo.
    pause
    exit /b 1
)
exit /b 0

:ensure_chromedriver
if exist "chromedriver.exe" (
    echo  ChromeDriver found next to project files.
    exit /b 0
)

where chromedriver >nul 2>&1
if not errorlevel 1 (
    echo  ChromeDriver found in PATH.
    exit /b 0
)

echo.
echo  ChromeDriver was not found. Downloading ChromeDriver %CHROMEDRIVER_VERSION%...
.venv\Scripts\python -c "import pathlib, shutil, tempfile, urllib.request, zipfile; url='%CHROMEDRIVER_URL%'; z=pathlib.Path('%CHROMEDRIVER_ZIP%'); urllib.request.urlretrieve(url, z); td=pathlib.Path(tempfile.mkdtemp(prefix='chromedriver-')); zipfile.ZipFile(z).extractall(td); src=next(td.rglob('chromedriver.exe')); shutil.copy2(str(src), 'chromedriver.exe'); print(' ChromeDriver downloaded:', pathlib.Path('chromedriver.exe').resolve())"
if errorlevel 1 (
    echo  [ERROR] Could not download/extract ChromeDriver.
    echo  Put matching chromedriver.exe next to these .bat files and run install again.
    echo.
    pause
    exit /b 1
)
exit /b 0

:check_chrome
set "CHROME_FOUND="
call :detect_chrome

if not defined CHROME_FOUND (
    call :install_local_chrome
    call :detect_chrome
)

if defined CHROME_FOUND (
    echo  Chrome found: %CHROME_FOUND%
    exit /b 0
)

echo.
echo  [WARNING] Chrome was not found automatically.
echo  On Windows 7 install Chrome 109, then run 2_RUN_BOT.bat.
echo  If you have an offline Chrome 109 installer, put it next to this file and run install again.
echo  Supported local installer names:
echo    ChromeStandaloneSetup64.exe
echo    ChromeStandaloneSetup.exe
echo    GoogleChromeStandaloneEnterprise64.msi
echo    GoogleChromeStandaloneEnterprise.msi
echo  Do not install latest Chrome: it does not support Windows 7.
echo.
exit /b 0

:detect_chrome
set "CHROME_FOUND="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if defined PF86 if exist "!PF86!\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=!PF86!\Google\Chrome\Application\chrome.exe"
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
goto :eof

:install_local_chrome
for %%I in ("ChromeStandaloneSetup64.exe" "ChromeStandaloneSetup.exe" "GoogleChromeStandaloneEnterprise64.msi" "GoogleChromeStandaloneEnterprise.msi") do (
    if exist "%%~I" (
        echo.
        echo  Chrome was not found. Running local Chrome installer: %%~I
        if /i "%%~xI"==".msi" (
            msiexec /i "%%~I" /qn /norestart
        ) else (
            start /wait "" "%%~I"
        )
        exit /b 0
    )
)
exit /b 0

:download_file
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072; (New-Object Net.WebClient).DownloadFile('%~1','%~2') } catch { exit 1 }"
if not errorlevel 1 exit /b 0

certutil -urlcache -split -f "%~1" "%~2" >nul 2>&1
if not errorlevel 1 exit /b 0

exit /b 1

:fail
echo.
echo  Install failed.
echo.
pause
exit /b 1
