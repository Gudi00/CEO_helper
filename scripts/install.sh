#!/usr/bin/env sh
# Установка СЭО helper на Linux и macOS из этой копии репозитория:
# сервер lms-tool, файл настроек и сборка расширения.
#
#   sh scripts/install.sh              обычная установка
#   sh scripts/install.sh --autostart  ещё и запускать сервер при входе в систему
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
AUTOSTART=0
[ "${1:-}" = "--autostart" ] && AUTOSTART=1

echo "== 1/3 Сервер =="
if ! command -v uv >/dev/null 2>&1; then
    echo "Устанавливаю uv (менеджер Python-пакетов)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
PATH="$HOME/.local/bin:$PATH"
export PATH

# uv сам скачает подходящий Python, если в системе его нет.
uv tool install --force --python 3.12 "$REPO_DIR/backend"
lms-tool init
[ "$AUTOSTART" -eq 1 ] && lms-tool autostart on

echo
echo "== 2/3 Расширение =="
EXT_DIR="$REPO_DIR/extension"
if ! command -v npm >/dev/null 2>&1; then
    echo "Node.js не найден — расширение не собрано."
    echo "Установите Node.js 20+ (https://nodejs.org) и запустите скрипт ещё раз."
elif [ -n "$(find "$EXT_DIR/dist" ! -user "$(id -un)" -print 2>/dev/null | head -n 1)" ]; then
    echo "В папке $EXT_DIR/dist есть файлы другого пользователя (например, после сборки в Docker) — расширение не собрано."
    echo "Удалите её (sudo rm -rf \"$EXT_DIR/dist\") и запустите скрипт ещё раз."
else
    (cd "$EXT_DIR" && npm install --no-audit --no-fund && npm run build)
    echo "Расширение собрано: $EXT_DIR/dist"
fi

cat <<MSG

== 3/3 Что дальше ==
  1. Впишите ключ нейросети в файл настроек (путь показан выше) и проверьте: lms-tool doctor
     Без ключа тоже можно — в расширении есть ручной режим.
  2. Запустите сервер: sh scripts/start.sh   (или просто: lms-tool run)
  3. В Chrome: chrome://extensions → «Режим разработчика» → «Загрузить распакованное расширение»
     → папка $EXT_DIR/dist
  4. Введите в окне расширения код сопряжения из окна сервера.

Подробная инструкция: docs/QUICKSTART.md
Если команда lms-tool не найдена — откройте новый терминал.
MSG
