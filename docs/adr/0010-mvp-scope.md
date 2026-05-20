# ADR 0010: MVP scope

## Status

Accepted, 2026-05-17

## Context

Стажировочный проект EPAM — ограниченный срок (~1-2 месяца на разработку).
Нужно сфокусироваться на минимальном работающем срезе, чтобы:

1. Показать end-to-end flow на защите.
2. Покрыть **основной use case пользователя** (текстовые multiple-choice
   тесты).
3. Иметь chronological roadmap для следующих фаз.

## Decision

### In scope (MVP)

**Функционал:**

- ✅ Текстовые multiple-choice вопросы:
  - Single-select (radio)
  - Multi-select (checkbox)
- ✅ Layouts: one-question-per-page + all-questions-on-one-page
- ✅ Три режима выполнения: assist, full_auto, step_by_step
- ✅ Стратегии доступа: CDP attach + manual login (стратегия "cookie
  export" — отложена)
- ✅ AI provider: Gemini Pro
- ✅ Persistence: SQLite, история, кеш ответов
- ✅ Stealth Mode A (natural через ext) + Mode B (paranoid через engine)
- ✅ Базовый UI: popup расширения с выбором режима, статусом, кнопкой
  старт/стоп

**Документация:**

- ✅ Все 10 ADR
- ✅ API contract (OpenAPI)
- ✅ WS protocol spec
- ✅ Question model JSON schema
- ✅ Development guide

**Тесты:**

- ✅ Unit тесты backend (>50% coverage на парсере, AI-провайдере, state
  machine)
- ✅ Fixture тесты на HTML-сэмплы (cross-language)
- ✅ Один manual E2E smoke сценарий: пройти настоящий тест в assist-режиме

### Out of scope (отложено)

**Phase 1.5:**
- ❌ Локальная Gemma 3 через Ollama (включаем после стабилизации Gemini-пайплайна)
- ❌ Cookie export расширением как стратегия доступа

**Phase 2:**
- ❌ Изображения в вопросах (MathJax PNG, схемы) — нужно vision
- ❌ Скриншот вопроса как фоллбэк для непарсимого HTML

**Phase 3:**
- ❌ Свободный текстовый ввод ответа (qtype_essay, qtype_shortanswer)
- ❌ Drag-and-drop matching (qtype_ddwtos, qtype_ddmarker)
- ❌ Сопоставление (qtype_match)
- ❌ Numerical (qtype_numerical)

**Phase 4 (полировка):**
- ❌ Дашборд статистики
- ❌ Экспорт в CSV
- ❌ Docker compose
- ❌ CI/CD
- ❌ Firefox версия расширения
- ❌ Multi-language UI

**Никогда:**
- ❌ Поддержка не-Moodle LMS
- ❌ Multi-user / cloud версия
- ❌ Шаринг ответов между пользователями

### Критерии "MVP готов"

1. **End-to-end happy path:** Пользователь открывает popup → выбирает
   assist → открывает тест в LMS → видит подсвеченные правильные
   варианты → кликает сам → завершает попытку.
2. **End-to-end full-auto:** Та же штука, но без участия пользователя
   после старта.
3. **История:** После завершения попытки `quiz.db` содержит строку
   `sessions` со score и связанные `answers`.
4. **Документация актуальна:** Все ADR соответствуют реальному коду на
   ±10%, изменения зафиксированы в новых ADR-supersession.
5. **Установка работает:** `git clone` + `cd backend && uv sync && uvicorn ...` +
   `cd extension && npm install && npm run build` + загрузка ext в Chrome
   = рабочий инструмент за <10 минут.

### Acceptance тест для защиты EPAM

Демо-сценарий на защите:
1. Показать архитектурную диаграмму (5 мин).
2. Запустить backend, открыть Chrome с расширением, открыть тестовый
   квиз в demo-Moodle (или sandbox-аккаунт BSUIR).
3. Показать assist: подсвечивает варианты, объясняет каждый ответ.
4. Показать full-auto: на ускоренном видео проходит тест за ~5 минут.
5. Показать SQLite базу через DBeaver: история, кеш, статистика.
6. Ответить на вопросы о stealth, выборе моделей AI, fallback логике.

## Consequences

### Положительные
- Чёткие границы → понятен объём работы и срок.
- Дорожная карта на следующие фазы → видна перспектива даже на MVP.
- Можно начинать с минимального slicе и доращивать.

### Отрицательные
- Часть вопросов в реальных тестах (картинки, формулы) не покрывается
  MVP. Mitigation: ext помечает их в UI как "не поддерживается, ответь
  сам", пользователь знает что ждать.
- Один AI-провайдер — точка отказа. Mitigation: Phase 1.5 близка
  (Ollama-fallback), при необходимости можно ускорить.

### Sized

- ~3-4 недели на backend + extension MVP (full-time)
- ~1 неделя на тесты и документацию-доводку
- ~1 неделя на полировку для защиты

## Alternatives considered

### Расширенный MVP с vision
Включить картинки сразу. Отвергнуто: vision усложняет AI prompt,
требует Phase-2-обвязки (screenshot canvas в ext, multimodal вызовы),
рискует не успеть к защите.

### Минимальный MVP без full-auto
Только assist-режим. Отвергнуто: full-auto — главная "вау"-фича для
комиссии EPAM, демо без неё проигрывает.

### MVP без бэкенда
Pure ext с прямым вызовом Gemini API из JS. Отвергнуто: см. [0001](0001-overall-architecture.md).
