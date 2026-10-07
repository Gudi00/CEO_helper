# Установка СЭО helper на Windows из этой копии репозитория:
# сервер lms-tool, файл настроек и сборка расширения.
# Проще всего запускать двойным щелчком по scripts\install.bat.
#
#   install.ps1              обычная установка
#   install.ps1 -Autostart   ещё и запускать сервер при входе в систему
param([switch]$Autostart)

$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent $PSScriptRoot

Write-Host "== 1/3 Сервер =="
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Устанавливаю uv (менеджер Python-пакетов)…"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

# uv сам скачает подходящий Python, если в системе его нет.
uv tool install --force --python 3.12 (Join-Path $RepoDir "backend")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
lms-tool init
if ($Autostart) { lms-tool autostart on }

Write-Host ""
Write-Host "== 2/3 Расширение =="
$ExtDir = Join-Path $RepoDir "extension"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js не найден - расширение не собрано."
    Write-Host "Установите Node.js 20+ (https://nodejs.org) и запустите установку ещё раз."
} else {
    Push-Location $ExtDir
    try {
        npm install --no-audit --no-fund
        if ($LASTEXITCODE -eq 0) { npm run build }
        if ($LASTEXITCODE -eq 0) { Write-Host "Расширение собрано: $ExtDir\dist" }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "== 3/3 Что дальше =="
Write-Host "  1. Впишите ключ нейросети в файл настроек (путь показан выше) и проверьте: lms-tool doctor"
Write-Host "     Без ключа тоже можно - в расширении есть ручной режим."
Write-Host "  2. Запустите сервер: двойной щелчок по scripts\start.bat   (или: lms-tool run)"
Write-Host "  3. В Chrome: chrome://extensions -> Режим разработчика -> Загрузить распакованное расширение"
Write-Host "     -> папка $ExtDir\dist"
Write-Host "  4. Введите в окне расширения код сопряжения из окна сервера."
Write-Host ""
Write-Host "Подробная инструкция: docs\QUICKSTART.md"
Write-Host "Если команда lms-tool не найдена - откройте новое окно терминала."
