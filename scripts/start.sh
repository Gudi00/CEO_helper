#!/usr/bin/env sh
# Запуск сервера СЭО helper на Linux и macOS. Окно показывает код сопряжения.
PATH="$HOME/.local/bin:$PATH"
export PATH

if ! command -v lms-tool >/dev/null 2>&1; then
    echo "Сервер не установлен. Сначала выполните: sh scripts/install.sh"
    exit 1
fi
exec lms-tool run
