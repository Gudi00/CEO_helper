#!/bin/sh
# macOS: двойной щелчок в Finder запускает установку.
cd "$(dirname "$0")/.." && sh scripts/install.sh
echo; printf "Нажмите Enter, чтобы закрыть окно… "; read -r _
