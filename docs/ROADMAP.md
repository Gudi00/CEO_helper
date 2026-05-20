# Roadmap

## Phase 1 — MVP (текущая цель)

**Goal:** работающий end-to-end flow для текстовых multiple-choice тестов
в Moodle BSUIR.

### Функционал
- [ ] Backend: FastAPI скелет, `/api/session/start`, `/api/question/answer`
- [ ] Backend: `GeminiProvider` с прокидкой prompt-а
- [ ] Backend: SQLite + миграции, таблицы `sessions`, `questions`, `answers`
- [ ] Extension: MV3 манифест, content script, popup
- [ ] Extension: парсер Moodle DOM (radio + checkbox, одно- и многостраничные)
- [ ] Extension: assist-режим — подсветка ответов в overlay
- [ ] Extension: step-by-step — overlay с подтверждением
- [ ] Backend + engine: full-auto через undetected-chromedriver + CDP attach
- [ ] Stealth-слой: random delays, mouse curves (только для engine)
- [ ] Логирование попыток

### Критерии готовности MVP
- Пройден реальный тест (любого размера) в assist-режиме — пользователь
  одобряет каждый ответ AI и кликает
- Пройден реальный тест в full-auto — engine завершает всё сам
- История попытки видна в SQLite с вопросами/ответами/score
- Документация устарела не больше, чем на 10% (всё, что есть в коде —
  отражено в ADR)

## Phase 1.5 — Локальная LLM fallback

Подключение Gemma 3 4B через Ollama. Активируется автоматически при
ошибках Gemini API (429, network, quota exhausted).

- [ ] `OllamaProvider` реализация
- [ ] Cascade-логика в фабрике провайдеров
- [ ] Бенчмарк точности: Gemini Pro vs Gemma 3 4B на одинаковых вопросах
- [ ] README: инструкция по установке Ollama

## Phase 2 — Vision / изображения

Многие вопросы BSUIR содержат формулы в виде PNG (MathJax) или схемы.

- [ ] Скриншот области вопроса в расширении (canvas.captureStream)
- [ ] Кодирование base64, передача в `/api/question/answer` как `image`
- [ ] Gemini Pro vision API — multimodal prompt
- [ ] Ollama vision: Gemma 3 4B-it (multimodal) или замена на LLaVA
- [ ] Тесты на fixture-страницах с картинками

## Phase 3 — Расширенные типы вопросов

- [ ] Текстовый ввод ответа (input/textarea) — генерация краткого ответа
- [ ] Drag-and-drop matching (DOM-парсинг сложнее, drag-симуляция в engine)
- [ ] Dropdown-вопросы
- [ ] "Сопоставление" вопросы Moodle

## Phase 4 — Полировка для защиты EPAM

- [ ] Dashboard на FastAPI (Jinja2 или статичный SPA) со статистикой
- [ ] Экспорт истории попыток в CSV
- [ ] Метрики: средняя уверенность AI, % правильных, time-to-answer
- [ ] Docker Compose для backend + Ollama
- [ ] CI: lint + tests на каждый PR

## Не делаем (out of scope)

- Поддержка других LMS (не Moodle) — отдельный продукт
- Мобильная версия — нет смысла без mobile-Moodle
- Cloud-deployment бэкенда — privacy: ключ и сессия LMS у пользователя
- Sharing аккаунтов / multi-user — это уже не "стажировочный проект"
