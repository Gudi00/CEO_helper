# ADR 0002: Технологический стек

## Status

Accepted, 2026-05-17

## Context

Гибридная архитектура (см. [0001](0001-overall-architecture.md)) требует
двух стеков: для расширения и для бэкенда. Цели выбора:

- Скорость разработки MVP (стажировка, ограничение по времени).
- Зрелость инструментов, понятная EPAM-комиссии.
- Поддержка нужных фич: undetected-chromedriver, Gemini SDK, локальная LLM,
  WebSocket, MV3.
- Минимум экзотики, максимум стандартных решений.

## Decision

### Backend

| Слой | Выбор | Альтернатива (rejected) |
|---|---|---|
| Язык | Python 3.12 | Node.js — Python имеет лучшие AI/ML библиотеки и undetected-chromedriver |
| Web framework | FastAPI | Flask — нет нативного WS; Litestar — мало known |
| ASGI server | Uvicorn | Hypercorn — Uvicorn популярнее |
| Models | Pydantic v2 | dataclasses — слабее валидация |
| ORM | SQLAlchemy 2.0 + Alembic | Raw sqlite3 — миграции вручную; Tortoise — менее стандартно |
| AI SDK | google-genai (новый) | google-generativeai — deprecated с 2026, EOL |
| Local LLM client | ollama-python | llama-cpp-python — сложнее в установке, нужно ручное управление моделями |
| Browser automation | undetected-chromedriver + Selenium | Playwright — отличный, но stealth-режим в нём слабее ([0007](0007-stealth-strategy.md)) |
| CDP | pychrome или встроенное в Selenium | прямой websocket — слишком низкоуровнево |
| HTTP-клиент | httpx | requests — нет async |
| Тесты | pytest + pytest-asyncio + httpx.AsyncClient | unittest — менее эргономичен |
| Линтинг | ruff + mypy | flake8+black+isort — ruff заменяет всё разом |
| Package | uv | poetry — uv быстрее и проще, новый стандарт |

### Extension

| Слой | Выбор | Альтернатива (rejected) |
|---|---|---|
| Manifest | V3 | MV2 — depreцирован Chrome |
| Язык | TypeScript 5 | JS — типы важны для синхронизации с backend |
| Build | Vite + @crxjs/vite-plugin | Webpack — медленнее и сложнее конфиг |
| UI | Vanilla TS + минимальный CSS | React/Preact — popup слишком маленький |
| Bundle target | Chrome 120+ | Cross-browser (Firefox) — Phase 4 |
| Хранилище | chrome.storage.local | localStorage — недоступно из service worker MV3 |
| Тесты | Vitest + Playwright Component Testing для DOM | Jest — slow на ESM |

### Внешние сервисы

- **Gemini Pro API** — primary AI. См. [0003](0003-ai-provider-strategy.md).
- **Ollama** — runtime для локальной Gemma 3 4B. Опциональная установка.
- **SQLite** — встроенная БД, никакого внешнего сервера. См. [0009](0009-data-persistence.md).

## Consequences

### Положительные
- Все технологии — mainstream, легко найти документацию и helpers.
- Python + FastAPI + SQLAlchemy — типичный EPAM-стек, хорошо смотрится на защите.
- Vite + @crxjs — современная сборка MV3 с HMR.
- ruff + mypy + Pydantic v2 — строгие типы и быстрый lint.

### Отрицательные
- `undetected-chromedriver` — менее активно поддерживается, чем Playwright.
  Mitigation: абстрагировать `Engine` интерфейс, чтобы можно было сменить.
- Vanilla TS для extension popup — больше ручного DOM-кода. Mitigation:
  popup минимальный, ~3-4 экрана.

### Sized

- Backend MVP: ~2000-3000 строк Python.
- Extension MVP: ~1000-1500 строк TS.

## Alternatives considered

### Single-language stack (только Node.js)
Заманчиво (shared types, один менеджер пакетов), но проигрывает по:
undetected-chromedriver (Python-exclusive), AI/ML экосистема, Ollama
интеграция, опыт EPAM-команд.

### Только Playwright (без undetected)
Playwright проще и мощнее (auto-waiting, лучшая отладка), но имеет узнаваемый
fingerprint (CDP, navigator.webdriver и т.д.). undetected-chromedriver
заточен именно под обход детектирования. Для full-auto-режима на BSUIR
LMS это критично.

### Tauri или Electron desktop-app вместо ext
Electron — лишний оверхед (отдельный Chromium). Tauri — нет browser-side
автоматизации в реальной сессии. Расширение элегантнее для нашего use case.
