#!/bin/sh
# macOS: двойной щелчок в Finder запускает сервер.
cd "$(dirname "$0")/.." && sh scripts/start.sh
echo; printf "Нажмите Enter, чтобы закрыть окно… "; read -r _
