# WebSocket Protocol Specification

## Endpoint

```
ws://127.0.0.1:8765/ws/{session_id}
```

`session_id` создаётся через `POST /api/session/start`. Один WS на сессию;
после `session/stop` или `attempt_completed` сервер закрывает соединение
с кодом 1000.

## Аутентификация

При коннекте клиент шлёт первое сообщение:

```json
{ "type": "auth", "token": "<X-Backend-Token из конфига>" }
```

Сервер отвечает либо `{"type": "ready"}`, либо закрывает с кодом 4401.

## Формат сообщений

Все сообщения — JSON одной строкой. Каждое сообщение имеет поле `type`.
Время в ISO 8601 UTC.

## Server → Client события

### session_state
Отправляется один раз при коннекте после auth, чтобы клиент знал текущее
состояние (на случай reconnect).

```json
{
  "type": "session_state",
  "session_id": "8f1d-...",
  "mode": "assist",
  "status": "running",
  "current_page": 3,
  "questions_answered": 2
}
```

### question_loaded
Расширение прислало вопрос (через `POST /api/question/answer`), backend
подтверждает приём.

```json
{
  "type": "question_loaded",
  "question_id": "q739284:5",
  "page_number": 4,
  "ts": "2026-05-17T14:23:11Z"
}
```

### answer_suggested
AI предложил ответ. Главное событие для UI расширения.

```json
{
  "type": "answer_suggested",
  "question_id": "q739284:5",
  "answer_indices": [2],
  "confidence": 0.87,
  "reasoning": "Параметр X определяется формулой Y, ответ B соответствует",
  "provider": "gemini-2.0-flash",
  "from_cache": false,
  "ts": "2026-05-17T14:23:12Z"
}
```

### engine_clicked
**Только** в `full_auto` режиме. Шлётся после имитированного клика.

```json
{
  "type": "engine_clicked",
  "question_id": "q739284:5",
  "option_index": 2,
  "delay_ms": 1420,
  "ts": "2026-05-17T14:23:18Z"
}
```

### page_advanced
Engine или расширение перешли на следующую страницу.

```json
{
  "type": "page_advanced",
  "from": 3,
  "to": 4,
  "ts": "2026-05-17T14:23:20Z"
}
```

### attempt_completed
Тест завершён и отправлен.

```json
{
  "type": "attempt_completed",
  "session_id": "8f1d-...",
  "score": 14,
  "max_score": 20,
  "duration_s": 443,
  "ts": "2026-05-17T14:30:30Z"
}
```

### error
Любая ошибка процесса. Не закрывает соединение, если не fatal.

```json
{
  "type": "error",
  "code": "AI_QUOTA_EXCEEDED",
  "message": "Gemini free tier exhausted",
  "fatal": false,
  "fallback": "ollama"
}
```

Известные коды:

| Code | Meaning | Fatal |
|---|---|---|
| `AI_QUOTA_EXCEEDED` | Gemini rate limit / quota | no (fallback) |
| `AI_TIMEOUT` | AI не ответил за N секунд | no |
| `AI_INVALID_RESPONSE` | AI вернул не JSON / неправильную структуру | no |
| `ENGINE_CDP_FAILED` | Не удалось подключиться по CDP | yes |
| `MOODLE_PARSE_FAILED` | Парсер не распознал страницу | yes |
| `MOODLE_LOGGED_OUT` | LMS отлогинил пользователя | yes |
| `BACKEND_INTERNAL` | Необработанная ошибка | yes |

### log
Опциональные debug-сообщения. По умолчанию выключены, активируются через
query-параметр `?debug=true` при WS-коннекте.

```json
{
  "type": "log",
  "level": "info",
  "msg": "Falling back to Ollama after Gemini 429",
  "ts": "2026-05-17T14:23:14Z"
}
```

## Client → Server команды

### confirm_answer
В `step_by_step` режиме: пользователь подтвердил предложенный ответ.

```json
{
  "type": "confirm_answer",
  "question_id": "q739284:5"
}
```

После этого ext имитирует клик локально и шлёт `page_advanced` (не обязательно
дожидаясь сервера) при переходе.

### reject_answer
Пользователь отклонил AI-ответ. Backend пометит в БД `was_correct=null`
с reasoning "user_rejected".

```json
{
  "type": "reject_answer",
  "question_id": "q739284:5",
  "user_answer_indices": [1]
}
```

### pause / resume
**Только** для `full_auto`. Pause останавливает цикл engine между вопросами;
resume продолжает.

```json
{ "type": "pause" }
{ "type": "resume" }
```

### abort
Жёстко остановить сессию. Эквивалент `POST /session/{id}/stop`.

```json
{ "type": "abort" }
```

## Reconnect стратегия

Расширение реализует exponential backoff:

```
attempt 1: immediate
attempt 2: +1s
attempt 3: +3s
attempt 4: +5s
attempt 5: +10s
после 5 неудач — показать "Backend offline" в popup
```

Backend при reconnect восстанавливает state через `session_state` event.
Если session уже completed/aborted — отвечает `error` с `fatal=true` и
закрывает.

## Heartbeat

Сервер шлёт `{"type": "ping"}` каждые 30s. Клиент отвечает
`{"type": "pong"}`. Это обходит timeouts любых прокси и помогает
обнаружить мёртвые соединения.

## Версионирование

Поле `protocol_version` в `session_state` (текущая — `"1"`). При смене
major-версии клиент рассинхронизированной версии получает `error` с кодом
`PROTOCOL_VERSION_MISMATCH` и `fatal=true`.

## Пример полного цикла assist-режима

```
←  session_state (status: running)
→  POST /api/question/answer { question: {...} }
←  HTTP 200 { answer_indices: [2], confidence: 0.87, ... }   # синхронный
←  answer_suggested (тот же контент, для WS-аудита)
(пользователь кликает в LMS)
←  page_advanced (from: 0, to: 1)
... повторяется N раз ...
←  attempt_completed { score: 14, max_score: 20 }
   (WS закрывается сервером)
```
