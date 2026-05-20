# ADR 0005: Связь расширения и бэкенда

## Status

Accepted, 2026-05-17

## Context

Расширение и backend живут на одной машине пользователя и обмениваются:

- **Командами** (синхронные запросы) — "вот вопрос, дай ответ", "запусти full-auto"
- **Событиями** (асинхронный стрим) — "вопрос N загружен", "AI предложил ответ",
  "engine кликнул", "тест завершён"

Кандидаты на транспорт:

| Транспорт | Pros | Cons |
|---|---|---|
| **HTTP REST + WS** | Стандарт, дебажится, FastAPI поддерживает оба | Два кода-пути |
| Native messaging | "Нативный" для расширений | Регистрация manifest в системе, сложнее установка |
| Только WS | Стрим естественен | RR-запросы через correlation_id неудобны |
| gRPC | Типизирован | Сложнее в браузере |
| MessagePort через iframe | Без backend сервера | Нет локальной LLM, нет SQLite |

## Decision

**HTTP REST + WebSocket на `127.0.0.1:8765`.**

REST для command-style (запрос → ответ), WS для server-push событий.
Расширение коннектит WS на старте сессии и слушает до закрытия.

### Hostname и порт

- `127.0.0.1` (не `localhost`) — избегаем DNS-резолва и неоднозначностей
  в Linux/Windows.
- Порт `8765` — далёкий от стандартных, маловероятен конфликт.
- При занятости — backend падает с явной ошибкой; пользователь
  переопределяет через `BACKEND_PORT` env var, расширение читает порт
  из своих настроек (popup).

### CORS

Backend разрешает только `chrome-extension://<ID>` через CORS middleware.
ID расширения фиксируется при первой установке (или используется
`extension_keys` в `manifest.json` для стабильного ID в dev).

### Аутентификация

Локальный сервис, нет multi-tenant. Но защита от случайного доступа
другого ПО на машине — `X-Backend-Token` header. Токен генерируется
backend при первом запуске, сохраняется в `~/.config/lms-tool/token`,
расширение его читает из popup-конфигурации (пользователь копирует
вручную при первой настройке). Это защищает от случайной утечки через
открытый порт.

### Эндпоинты (краткая сводка, полная — в `specs/api-contract.yaml`)

```
POST   /api/session/start              { mode, cmid, access_strategy }
                                       → { session_id, ws_url }
POST   /api/session/{id}/stop          → 204
GET    /api/session/{id}                → SessionState

POST   /api/question/answer            { session_id, question }
                                       → AnswerResult
POST   /api/question/{q_hash}/feedback { was_correct }   # для будущего тюнинга
GET    /api/question/{q_hash}/cached    → AnswerResult | 404

GET    /api/history                     [Attempt[]]
GET    /api/history/{attempt_id}        Attempt

POST   /api/engine/start               { session_id, access_strategy }   # full-auto
POST   /api/engine/stop                { session_id }

WS     /ws/{session_id}                server→client events stream
```

### WS protocol (events)

Сервер шлёт JSON-сообщения:

```json
{ "type": "answer_suggested", "question_id": "q1", "answer_indices": [2], "confidence": 0.87, "reasoning": "..." }
{ "type": "engine_clicked",   "question_id": "q1", "delay_ms": 1400 }
{ "type": "page_advanced",    "from": 0, "to": 1 }
{ "type": "attempt_completed","score": 14, "max_score": 20, "duration_s": 443 }
{ "type": "error",            "code": "AI_QUOTA_EXCEEDED", "message": "..." }
```

Клиент шлёт команды:

```json
{ "type": "confirm_answer",   "question_id": "q1" }    # step-by-step
{ "type": "reject_answer",    "question_id": "q1" }
{ "type": "pause" }
{ "type": "resume" }
```

Полная спека — [specs/ws-protocol.md](../specs/ws-protocol.md).

### Синхронизация моделей данных

`NormalizedQuestion` и `AnswerResult` определены один раз в Pydantic
(backend) и в TypeScript (extension). Чтобы избежать дрейфа — варианты:

1. **Генерация типов** из OpenAPI: backend экспортит OpenAPI → запускается
   `openapi-typescript` → файл `extension/src/shared/types.gen.ts`.
2. **Ручное дублирование** + тесты на симметрию (JSON-fixture парсится
   обеими сторонами).

**Выбран:** вариант 1 (codegen из OpenAPI) — единый источник истины и
автоматическая защита от дрейфа. Добавить npm script `npm run codegen`
в extension/package.json, который дёргает локальный backend и генерит
типы.

## Consequences

### Положительные
- Стандартный, легко отлаживаемый стек.
- WebSocket даёт live-обновления — UX в popup намного приятнее.
- Кодогенерация защищает от расхождения типов.

### Отрицательные
- Backend должен быть запущен ДО открытия расширения — иначе ext шлёт
  fetch на мёртвый порт. Mitigation: popup показывает "Backend offline,
  start it" с инструкцией.
- Локальный токен в файле — нужно объяснить пользователю где он лежит.

### Связанные риски

- **Порт занят другим приложением**: явная ошибка при запуске backend.
- **Backend перезапускается во время сессии**: WS дисконнектится, ext
  пытается reconnect 5 раз с backoff, потом сообщает ошибку.

## Alternatives considered

### Только Server-Sent Events (SSE) вместо WS
Проще (HTTP-stream), но не bi-directional. Шаг step-by-step (клиент
шлёт confirm) сложнее. WS даёт single channel для обоих направлений.

### MQTT через embedded broker
Overkill для двух процессов на одной машине.

### Chrome extension messages с offscreen-document
Можно держать состояние в offscreen-документе, но нет Python — нельзя
запустить локальную LLM. Не применимо.
