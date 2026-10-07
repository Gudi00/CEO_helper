@echo off
rem Windows: двойной щелчок запускает установку СЭО helper.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
