@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запуск бота автопостинга MAX...
py -3 bot.py
echo.
echo Бот остановлен. Нажмите любую клавишу для выхода.
pause >nul
