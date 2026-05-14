@echo off
chcp 65001 >nul
echo Creating krisha-bot-windows7-py38.zip...

if exist "..\krisha-bot-windows7-py38.zip" del "..\krisha-bot-windows7-py38.zip"
if exist ".\tests\__pycache__" rmdir /s /q ".\tests\__pycache__"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$paths='.\*.py','.\*.txt','.\*.bat','.\*.md','.\config.json','.\.env.example','.\Dockerfile','.\run.sh','.\prompts','.\tests'; $optional='.\1_INSTALL_ONCE.exe','.\2_RUN_BOT.exe','.\chromedriver.exe','.\python-3.8.10-amd64.exe','.\python-3.8.10.exe','.\ChromeStandaloneSetup64.exe','.\ChromeStandaloneSetup.exe','.\GoogleChromeStandaloneEnterprise64.msi','.\GoogleChromeStandaloneEnterprise.msi'; foreach ($item in $optional) { if (Test-Path -LiteralPath $item) { $paths += $item } }; Compress-Archive -Path $paths -DestinationPath '..\krisha-bot-windows7-py38.zip' -Force"
if errorlevel 1 (
  echo.
  echo [ERROR] Could not create krisha-bot-windows7-py38.zip.
  echo.
  pause
  exit /b 1
)

echo.
echo Done: ..\krisha-bot-windows7-py38.zip
echo.
echo Not packaged: .venv, .env, contacted.db, logs, screenshots, Selenium Chrome profile.
echo Optional installers are packaged only when they are present next to make_zip.bat.
echo.
pause
