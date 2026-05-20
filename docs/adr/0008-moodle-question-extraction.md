# ADR 0008: Извлечение вопросов из Moodle DOM

## Status

Accepted, 2026-05-17

## Context

Стандартный Moodle quiz рендерит вопросы в predictable HTML. Поддерживаемые
в MVP типы:

- `qtype_multichoice` — radio buttons (один правильный ответ)
- `qtype_multichoice` — checkboxes (несколько правильных, заголовок
  "Выберите один или несколько")

Структура страницы:

```html
<div class="que multichoice ..." id="question-{attemptId}-{qNum}">
  <div class="content">
    <div class="qtext">
      <p>Текст вопроса...</p>
    </div>
    <div class="ablock">
      <div class="answer">
        <div class="r0">
          <input type="radio" name="q{attemptId}:{qNum}_answer" value="1" id="q...">
          <label for="q...">
            <span class="answernumber">1.</span>
            Вариант ответа A
          </label>
        </div>
        <div class="r1">...</div>
      </div>
    </div>
  </div>
</div>
```

Варианты layout:
- **One-per-page**: один `.que` на странице, плюс кнопки "Предыдущая/Следующая".
- **All-on-page**: множество `.que` на одной странице, кнопка "Закончить попытку".

## Decision

### Нормализованная модель

```typescript
type NormalizedQuestion = {
  id: string;                  // q{attemptId}:{qNum}
  hash: string;                // SHA-256(text + options.map(o=>o.text).sorted)
  type: "single_choice" | "multiple_choice";
  text: string;                // plain text вопроса (HTML stripped, formulas из MathJax → "$...$" placeholder)
  options: {
    index: number;             // 0-based, для prompt
    value: string;             // value attribute из <input> — для submit
    text: string;              // plain text варианта
  }[];
  metadata: {
    page_number: number;
    attempt_id: string;
    cmid: string;
    has_images: boolean;       // MVP: если true, помечаем но не обрабатываем
  };
};
```

Подробная JSON Schema — [specs/question-model.md](../specs/question-model.md).

### Селекторы (Moodle 4.x)

| Что | Селектор |
|---|---|
| Контейнер вопроса | `.que[id^="question-"]` |
| Текст вопроса | `.qtext` |
| Варианты ответов | `.answer > div[class^="r"]` |
| Radio/checkbox | `input[type=radio][name*="_answer"]`, `input[type=checkbox][name*="_answer"]` |
| Текст варианта | `label` (после `<input>`) — исключая `.answernumber` префикс |
| Тип (single/multiple) | По `input.type` (radio → single, checkbox → multiple) |
| Кнопка "Следующая" | `input.mod_quiz-next-nav, button[name="next"]` |
| Кнопка "Закончить" | `input.mod_quiz-finish-nav, button[name="finishattempt"]` |
| Подтверждение submit | `button[name="confirm"]` в overlay |

### Парсинг в расширении (TS)

`extension/src/content/moodle-parser.ts`:

```typescript
export function parseQuestionsOnPage(doc: Document): NormalizedQuestion[] {
  return Array.from(doc.querySelectorAll('.que[id^="question-"]'))
    .map(parseSingleQuestion);
}
```

`parseSingleQuestion`:
1. Извлечь `id` из `id="question-{attempt}-{qNum}"`.
2. Текст: `.qtext.innerText.trim()` (innerText даёт уже-rendered текст,
   формулы превращаются в Unicode где возможно).
3. Тип: по `input[type]` первого инпута в `.answer`.
4. Опции: для каждого `.answer > div`:
   - `value` = `input.value`
   - `text` = `label.innerText.replace(/^\d+\.\s*/, '')` (убираем "1. " префикс)
   - `index` = по порядку
5. `has_images` = `.qtext img.length > 0 || .answer img.length > 0`.
6. `hash` — стабильный SHA-256 от текста + sorted options (для кеша).

### Парсинг в backend (Python) для engine-режима

`backend/src/moodle/parser.py` — дублирует логику парсинга для engine,
который читает DOM через WebDriver. Используется BeautifulSoup4 для
парсинга HTML, либо Selenium-нативные find_elements.

Чтобы не было drift между TS и Python:
- Общие HTML-fixtures в `tests/fixtures/moodle/` (по одной на тип вопроса).
- Тесты с обеих сторон парсят fixture → сравнивают с эталонным
  `expected.json`.
- При расхождении тест падает.

### MutationObserver (расширение)

Content script регистрирует MutationObserver на `document.body`. Когда
видит добавление `.que` элемента — парсит и шлёт в backend. Это
покрывает оба layout-а:

- one-per-page: после `Next.click()` Moodle перерендерит content → MO
  ловит.
- all-on-page: первая загрузка → MO видит все сразу.

```typescript
const obs = new MutationObserver((mutations) => {
  const newQuestions = mutations
    .flatMap(m => Array.from(m.addedNodes))
    .filter(n => n.nodeType === 1)
    .flatMap(n => Array.from((n as Element).querySelectorAll('.que')))
    .map(parseSingleQuestion);
  newQuestions.forEach(q => api.sendQuestion(q));
});
obs.observe(document.body, { childList: true, subtree: true });
```

### Подсветка / клик в DOM

Найти label по id вопроса и индексу варианта:

```typescript
function getOptionLabel(questionId: string, optionIndex: number): HTMLLabelElement {
  const container = document.getElementById(questionId);
  const answers = container.querySelectorAll('.answer > div[class^="r"]');
  return answers[optionIndex].querySelector('label');
}
```

Подсветка в assist:
```typescript
label.classList.add('lms-tool-suggested');
label.dataset.lmsConfidence = (confidence * 100).toFixed(0);
```

Клик в step_by_step (через native event):
```typescript
const input = label.querySelector<HTMLInputElement>('input');
const rect = input.getBoundingClientRect();
const opts = { bubbles: true, cancelable: true,
               clientX: rect.left + rect.width/2,
               clientY: rect.top + rect.height/2 };
input.dispatchEvent(new MouseEvent('mousedown', opts));
input.dispatchEvent(new MouseEvent('mouseup', opts));
input.dispatchEvent(new MouseEvent('click', opts));
```

## Consequences

### Положительные
- Чёткая нормализация — AI получает консистентный формат, не зависит от
  Moodle-разметки.
- Кеширование по hash — повтор того же вопроса в новой попытке = бесплатно.
- Поддержка обоих layout-ов через MutationObserver.

### Отрицательные
- Парсер привязан к Moodle 4.x классам. При мажорном обновлении (Moodle 5)
  селекторы могут поменяться. Mitigation: ADR-rule о проверке селекторов
  при upgrade, fixture-тесты ловят регрессии.
- Дублирование парсера в TS и Py. Mitigation: shared fixtures + cross-check
  тесты.

## Alternatives considered

### XPath вместо CSS селекторов
XPath мощнее, но менее читаемо. CSS достаточно для нашей задачи.

### Парсер только в backend, ext шлёт raw HTML
Привело бы к передаче ~50КБ HTML на каждый вопрос через WS. Парсинг в ext
эффективнее.

### Снимать скриншот вопроса и слать AI как изображение
Работает, но: 1) ломает кеширование (хеш изменяется от рендера), 2) тратит
vision-quota, 3) для текстовых вопросов overkill. Делаем только в Phase 2
для изображённых формул.

### Использовать Moodle Web Services API
Moodle имеет REST API (`/webservice/rest/server.php`), но для quiz
участник не имеет доступа к правильным ответам, только к своим попыткам.
Полезно для логирования (получить score после попытки), но не для
извлечения вопросов.
