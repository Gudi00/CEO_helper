# Development

## Структура репозитория

```
СЭО_bot/
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md          ← этот файл
│   ├── ROADMAP.md
│   ├── adr/                    ← ADR 0001-0010
│   └── specs/                  ← OpenAPI, JSON-schema, WS-протокол
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── src/
│   │   ├── main.py             ← uvicorn entrypoint
│   │   ├── api/                ← FastAPI routers (session, question, history)
│   │   ├── ai/
│   │   │   ├── base.py         ← AIProvider Protocol
│   │   │   ├── gemini.py
│   │   │   └── ollama.py
│   │   ├── automation/
│   │   │   ├── engine.py       ← undetected-chromedriver runner
│   │   │   └── cdp.py          ← CDP attach helper
│   │   ├── moodle/
│   │   │   ├── parser.py       ← DOM → NormalizedQuestion (для engine)
│   │   │   └── types.py        ← pydantic models
│   │   ├── persistence/
│   │   │   ├── db.py           ← SQLAlchemy / sqlite3
│   │   │   ├── models.py
│   │   │   └── migrations/
│   │   └── stealth/
│   │       ├── delays.py       ← randomized human-like timings
│   │       └── mouse.py        ← Bezier curves
│   └── tests/
├── extension/
│   ├── manifest.json           ← MV3, host_permissions: lms.bsuir.by + localhost
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts          ← или webpack — build to dist/
│   └── src/
│       ├── background/
│       │   └── service-worker.ts
│       ├── content/
│       │   ├── moodle-parser.ts
│       │   ├── overlay.ts      ← подсветка вариантов
│       │   └── content.ts      ← entrypoint
│       ├── popup/
│       │   ├── index.html
│       │   └── popup.ts        ← настройки, выбор режима, статус
│       └── shared/
│           ├── api-client.ts   ← обёртка над HTTP/WS бэкенда
│           └── types.ts        ← shared с backend через codegen
└── .gitignore
```

## Backend

### Стек

- Python 3.12+
- FastAPI + Uvicorn
- Pydantic v2 для моделей
- SQLAlchemy 2.0 + Alembic (SQLite в dev, легко переключить на Postgres)
- google-genai (Gemini SDK; старый `google-generativeai` deprecated с 2026)
- ollama-python (локальная Gemma)
- undetected-chromedriver + selenium для engine-режима
- pytest + pytest-asyncio + httpx для тестов

### Запуск (после реализации)

```bash
cd backend
uv sync                          # или: python -m venv .venv && pip install -e .
cp .env.example .env             # вписать GEMINI_API_KEY
alembic upgrade head             # инициализация SQLite
uvicorn src.main:app --port 8765 --reload
```

### Переменные окружения

| Var | Default | Описание |
|---|---|---|
| `GEMINI_API_KEY` | — | Ключ Gemini API (required) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Модель по умолчанию |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API |
| `OLLAMA_MODEL` | `gemma3:4b` | Локальная модель |
| `DATABASE_URL` | `sqlite:///./quiz.db` | SQLite файл |
| `CDP_PORT` | `9222` | Порт CDP подключения к Chrome |
| `LOG_LEVEL` | `INFO` | |

## Extension

### Стек

- Manifest V3
- TypeScript 5
- Vite (быстрый dev-build + HMR через `@crxjs/vite-plugin`)
- Минимальный UI — vanilla TS + CSS, без React. Цель — лёгкий popup.

### Сборка

```bash
cd extension
npm install
npm run build         # → dist/
npm run dev           # watch mode
```

Установка в Chrome:
1. `chrome://extensions/` → Developer mode
2. Load unpacked → выбрать `extension/dist`

### Permissions (manifest.json)

```json
{
  "manifest_version": 3,
  "host_permissions": [
    "https://lms.bsuir.by/*",
    "http://127.0.0.1:8765/*"
  ],
  "permissions": ["storage", "activeTab", "scripting"]
}
```

## Локальная Gemma (опционально, Phase 1.5)

```bash
# Ollama install: https://ollama.com/download
ollama pull gemma3:4b           # ~3.5 ГБ VRAM
ollama serve                    # на :11434
```

В `.env` бэкенда:
```
OLLAMA_MODEL=gemma3:4b
```

Бэкенд переключается на Ollama автоматически при ошибках Gemini
(quota, 429, network) — см. [adr/0003-ai-provider-strategy.md](adr/0003-ai-provider-strategy.md).

## CDP-режим (для engine)

Запустить Chrome с remote debugging:

```bash
google-chrome --remote-debugging-port=9222 \
              --user-data-dir=$HOME/.config/google-chrome
```

После этого бэкенд может подключиться к существующей сессии (где пользователь
уже залогинен в LMS) и работать в ней. Это — основной механизм для full-auto
режима без необходимости отдельного логина в Playwright-окне.

## Тестирование

- `backend/tests/` — pytest. Юниты на парсер DOM, AI-провайдеры (с моками
  Gemini), state-машину режимов.
- Интеграционные тесты с реальным Moodle — отдельный optional набор,
  запускается только локально с реальной сессией.
- E2E теста на сам тест — нет (рискованно для аккаунта). Вместо этого —
  HTML-fixtures страниц Moodle в `tests/fixtures/`.
