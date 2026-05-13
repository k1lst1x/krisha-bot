@echo off
chcp 65001 >nul
echo Creating krisha-bot-windows7-py38.zip...

if exist "..\krisha-bot-windows7-py38.zip" del "..\krisha-bot-windows7-py38.zip"

powershell -NoProfile -Command ^
  "Compress-Archive -Path ^
    '.\*.py', ^
    '.\*.txt', ^
    '.\*.bat', ^
    '.\*.md', ^
    '.\config.json', ^
    '.\.env.example', ^
    '.\Dockerfile', ^
    '.\run.sh', ^
    '.\prompts', ^
    '.\tests' ^
  -DestinationPath '..\krisha-bot-windows7-py38.zip' -Force"

echo.
echo Done: ..\krisha-bot-windows7-py38.zip
echo.
echo Not packaged: .venv, .env, contacted.db, logs, screenshots, Selenium Chrome profile.
echo.
pause
