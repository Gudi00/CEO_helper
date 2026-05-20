# Архитектура

## Обзор

Система состоит из двух деплоимых артефактов и внешних зависимостей:

1. **Chrome MV3 Extension** — UI, content scripts для разбора DOM Moodle,
   overlay-подсветка вариантов ответа, popup с настройками.
2. **Local Backend** (Python 3.12 + FastAPI) — AI-провайдер, история попыток
   (SQLite), engine-режим автоматизации через undetected-chromedriver,
   WebSocket для стрима событий.
3. **AI Provider** — Gemini Pro API (cloud) с fallback на локальную Gemma 3
   через Ollama.

Расширение и бэкенд общаются по HTTP+WebSocket на `127.0.0.1:8765`.
Расширение делает всю работу с DOM теста; бэкенд отвечает только за
"мозги" и хранилище. Это даёт максимальную стелс-незаметность для
основного use-case (расширение работает в реальной сессии пользователя
без любых внешних автоматизационных следов).

## Component diagram

```mermaid
graph TB
    subgraph User_Browser["Пользовательский Chrome"]
        LMS[lms.bsuir.by Moodle UI]
        Ext[MV3 Extension<br/>content + popup + bg]
    end

    subgraph Local["Localhost"]
        BE[FastAPI Backend<br/>:8765]
        DB[(SQLite<br/>history + cache)]
        Engine[Engine Mode<br/>undetected-chromedriver]
    end

    subgraph Cloud["Cloud / Local LLM"]
        Gemini[Gemini Pro API]
        Ollama[Ollama runtime<br/>Gemma 3 4B]
    end

    LMS <--> Ext
    Ext <-->|HTTP + WS| BE
    BE --> DB
    BE -.fallback.-> Ollama
    BE --> Gemini
    BE -.engine mode.-> Engine
    Engine --> LMS
```

## Высокоуровневые потоки

### Assist mode (рекомендуемый для пользователя)

```mermaid
sequenceDiagram
    participant U as User
    participant LMS as Moodle Quiz Page
    participant CS as Content Script
    participant BG as BG Service Worker
    participant BE as Backend (FastAPI)
    participant AI as Gemini Pro

    U->>LMS: Открыл тест, нажал "Начать попытку"
    CS->>CS: MutationObserver видит вопросы
    CS->>BG: question_loaded(NormalizedQuestion)
    BG->>BE: POST /api/question/answer
    BE->>AI: prompt с вопросом и вариантами
    AI-->>BE: { answer_indices, confidence, reasoning }
    BE-->>BG: AnswerResult
    BG-->>CS: highlight_answers(indices, confidence)
    CS->>LMS: добавляет CSS-класс на правильные варианты
    U->>LMS: Кликает сам (естественный stealth)
```

### Full-auto mode (engine)

```mermaid
sequenceDiagram
    participant U as User
    participant Ext as Extension (popup)
    participant BE as Backend
    participant Eng as Engine (undetected-chromedriver)
    participant LMS as Moodle Quiz Page
    participant AI as Gemini Pro

    U->>Ext: Запуск full-auto, cmid=305095
    Ext->>BE: POST /api/session/start { mode: full_auto, cmid }
    BE->>Eng: spawn Chrome attach via CDP к существующему профилю
    loop по страницам теста
        Eng->>LMS: navigate / scroll
        Eng->>Eng: read DOM → NormalizedQuestion
        Eng->>AI: ask
        AI-->>Eng: answer
        Eng->>LMS: human-like mouse curve → click radio
        Eng->>LMS: random delay 0.8-2.5s → click "Следующая"
    end
    Eng->>LMS: submit attempt
    Eng-->>BE: attempt_completed (score, time)
    BE-->>Ext: WS attempt_completed
```

### Step-by-step mode

Гибрид. AI отвечает, ext показывает предложение в overlay над вариантом
("AI: вариант 2, 87% уверенности — Enter подтвердить, ← отменить"), ждёт
явный input от пользователя, затем имитирует клик сам или ждёт ручного
клика — в зависимости от подтверждения.

## Граница ответственности

| Что | Где |
|---|---|
| DOM-парсинг Moodle | Extension (content script) |
| Подсветка ответа в DOM | Extension (content script + injected CSS) |
| Имитация клика, mouse curves | Backend в engine-режиме; Extension в browser-режиме |
| HTTP-вызовы к AI | Backend (никогда не из расширения — CORS, скрытие ключа) |
| Хранение истории | Backend (SQLite) |
| Кеширование ответов | Backend (по SHA-256 хешу нормализованного вопроса) |
| Настройки пользователя | Extension (`chrome.storage.sync`) |
| Stealth-логика для engine | Backend (`backend/src/stealth/`) |

## Что вне scope MVP

См. [adr/0010-mvp-scope.md](adr/0010-mvp-scope.md). Кратко: изображения
(MathJax, схемы), текстовый ввод ответов, drag-and-drop вопросы,
локальная Gemma (отложена на Phase 1.5).

## Дальше

- Архитектурные решения и альтернативы → [adr/](adr/)
- Контракты API и форматы данных → [specs/](specs/)
- Запуск и структура кода → [DEVELOPMENT.md](DEVELOPMENT.md)
