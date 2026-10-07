@echo off
rem Windows: двойной щелчок запускает сервер СЭО helper. Окно показывает код сопряжения.
chcp 65001 >nul
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where lms-tool >nul 2>nul
if errorlevel 1 (
  echo Сервер не установлен. Сначала запустите scripts\install.bat
  pause
  exit /b 1
)
lms-tool run
pause
