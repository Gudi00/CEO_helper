import '../models/question.dart';
import '../models/question_type.dart';

/// Prompt construction for Gemini. Ported in spirit from the original project's
/// `backend/src/ai/prompts.py` and re-tuned for a **foreign-language /
/// translation / humanities** university context, which is where this app must
/// score well.

/// Appended to every system prompt (default or custom). The model MUST see this
/// regardless of a custom role, otherwise JSON parsing breaks.
const String jsonFormatInstruction = '''
Отвечай СТРОГО в формате JSON, БЕЗ markdown, БЕЗ преамбулы:
{
  "answer_indices": [<список 0-based индексов; [] для текстового вопроса>],
  "answer_text": "<строка-ответ для текстового вопроса; "" для выбора>",
  "confidence": <float 0..1>,
  "reasoning": "<краткое — до 200 символов — обоснование>"
}

Для single_choice — answer_indices содержит ровно один индекс, answer_text = "".
Для multiple_choice — один или несколько индексов, answer_text = "".
Для text_input — answer_indices = [], answer_text содержит готовый ответ.
confidence: 0.95+ абсолютно уверен · 0.75-0.94 уверен · 0.5-0.74 сомнения · <0.5 угадывание.''';

/// Default expert role, specialized for a translators'/humanities faculty.
const String _defaultRole = '''
Ты — эксперт-филолог, профессиональный переводчик и преподаватель иностранных
языков в вузе для переводчиков и гуманитариев. Ты глубоко знаешь грамматику
(времена, наклонения, залог, падежи, артикли, согласование), лексику, идиомы и
устойчивые сочетания, «ложных друзей переводчика», стилистику и регистр, теорию
и практику перевода, лингвистику, страноведение и литературу.

Алгоритм мышления (выполняй внутренне перед ответом):
  1. Определи язык вопроса и вариантов и область (грамматика, лексика, перевод,
     лингвистика, страноведение).
  2. Перефразируй, что именно спрашивают.
  3. Для каждого варианта объясни, почему он верен или неверен — с опорой на
     норму языка, узус и идиоматичность, а не на дословность.
  4. Учитывай регистр, коллокации и грамматическую форму (правильный артикль,
     время, падеж, согласование).
  5. Выбери ответ. Отвечай на ТОМ ЖЕ языке, на котором задан вопрос/варианты.
  6. Если 2+ варианта правдоподобны — confidence ≤ 0.7.

Для текстовых вопросов (text_input): дай готовый ответ в нужной грамматической
форме, без пояснений в самом ответе (пояснение — только в reasoning). Если это
перевод — выбери самый точный и естественный вариант, а не подстрочник.''';

/// Effective system prompt: (custom role or default) + optional target-language
/// hint + the mandatory JSON block.
String buildSystemPrompt({String? custom, String? targetLanguage}) {
  final role = (custom != null && custom.trim().isNotEmpty)
      ? custom.trim()
      : _defaultRole;
  final langHint = (targetLanguage != null && targetLanguage.trim().isNotEmpty)
      ? '\n\nЦелевой язык теста: ${targetLanguage.trim()}. '
          'Если вопрос на этом языке — рассуждай как его носитель.'
      : '';
  return '$role$langHint\n\n$jsonFormatInstruction';
}

/// Renders the per-question user message.
String renderUserPrompt(Question q) {
  switch (q.type) {
    case QuestionType.singleChoice:
    case QuestionType.multipleChoice:
      final human = q.type == QuestionType.singleChoice
          ? 'выбери ОДИН правильный вариант'
          : 'выбери ОДИН ИЛИ НЕСКОЛЬКО правильных вариантов';
      final optionsBlock = q.options
          .map((o) => '  ${o.index}) ${o.text}')
          .join('\n');
      return 'Тип вопроса: $human\n'
          'Вопрос:\n${q.text}\n\n'
          'Варианты ответа (индексы 0-based):\n$optionsBlock\n\n'
          'Верни ТОЛЬКО JSON-объект, описанный в system message '
          '(answer_indices заполнен, answer_text = "").';
    case QuestionType.textInput:
      return 'Тип вопроса: впиши свободный текстовый ответ.\n'
          'Вопрос:\n${q.text}\n\n'
          'Напиши готовый ответ в нужной грамматической форме. Верни ТОЛЬКО '
          'JSON-объект (answer_text заполнен, answer_indices = []).';
  }
}
