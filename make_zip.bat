@echo off
chcp 65001 >nul
echo Создаю архив krisha-bot.zip...

:: Удалить старый архив если есть
if exist "..\krisha-bot.zip" del "..\krisha-bot.zip"

:: Упаковать нужные файлы (без .venv, .env, storage-state, базы данных, логов)
powershell -NoProfile -Command ^
  "Compress-Archive -Path ^
    '.\*.py', ^
    '.\*.txt', ^
    '.\*.bat', ^
    '.\config.json', ^
    '.\.env.example', ^
    '.\Dockerfile', ^
    '.\README.md', ^
    '.\run.sh', ^
    '.\prompts', ^
    '.\tests' ^
  -DestinationPath '..\krisha-bot.zip' -Force"

echo.
echo Готово! Файл: ..\krisha-bot.zip
echo.
echo Что внутри:
echo   - start.bat       (запуск одним кликом)
echo   - .env.example    (шаблон настроек)
echo   - requirements.txt
echo   - все .py файлы
echo.
pause
