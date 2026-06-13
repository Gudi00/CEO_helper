import 'package:flutter_test/flutter_test.dart';
import 'package:google_form_app/ai/answer_parser.dart';
import 'package:google_form_app/models/question.dart';
import 'package:google_form_app/models/question_type.dart';

Question _choice(QuestionType type) => Question(
      id: 'f:0',
      hash: '',
      type: type,
      text: 'q',
      options: const [
        Option(index: 0, value: 'a', text: 'a'),
        Option(index: 1, value: 'b', text: 'b'),
        Option(index: 2, value: 'c', text: 'c'),
      ],
      formId: 'f',
      index: 0,
    );

Question _text() => const Question(
      id: 'f:1',
      hash: '',
      type: QuestionType.textInput,
      text: 'translate',
      options: [],
      formId: 'f',
      index: 1,
    );

void main() {
  test('single_choice: valid single index', () {
    final r = parseAndValidate(
      '{"answer_indices":[1],"confidence":0.9,"reasoning":"x"}',
      _choice(QuestionType.singleChoice),
      provider: 'm',
    );
    expect(r.answerIndices, [1]);
    expect(r.answerText, isNull);
    expect(r.confidence, 0.9);
  });

  test('single_choice: extra indices are trimmed and confidence discounted', () {
    final r = parseAndValidate(
      '{"answer_indices":[1,2],"confidence":1.0}',
      _choice(QuestionType.singleChoice),
      provider: 'm',
    );
    expect(r.answerIndices, [1]);
    expect(r.confidence, closeTo(0.7, 1e-9));
  });

  test('multiple_choice: multiple indices kept', () {
    final r = parseAndValidate(
      '{"answer_indices":[0,2],"confidence":0.8}',
      _choice(QuestionType.multipleChoice),
      provider: 'm',
    );
    expect(r.answerIndices, [0, 2]);
  });

  test('index out of range throws', () {
    expect(
      () => parseAndValidate(
        '{"answer_indices":[5],"confidence":0.8}',
        _choice(QuestionType.singleChoice),
        provider: 'm',
      ),
      throwsA(isA<InvalidAnswer>()),
    );
  });

  test('empty indices for choice throws', () {
    expect(
      () => parseAndValidate(
        '{"answer_indices":[],"confidence":0.5}',
        _choice(QuestionType.singleChoice),
        provider: 'm',
      ),
      throwsA(isA<InvalidAnswer>()),
    );
  });

  test('text_input: answer_text required', () {
    final r = parseAndValidate(
      '{"answer_indices":[],"answer_text":"das Haus","confidence":0.85}',
      _text(),
      provider: 'm',
    );
    expect(r.answerText, 'das Haus');
    expect(r.answerIndices, isEmpty);
  });

  test('text_input: empty answer_text throws', () {
    expect(
      () => parseAndValidate(
        '{"answer_text":"  ","confidence":0.85}',
        _text(),
        provider: 'm',
      ),
      throwsA(isA<InvalidAnswer>()),
    );
  });

  test('strips ```json fences', () {
    final r = parseAndValidate(
      '```json\n{"answer_indices":[0],"confidence":0.6}\n```',
      _choice(QuestionType.singleChoice),
      provider: 'm',
    );
    expect(r.answerIndices, [0]);
  });

  test('confidence clamped to 0..1', () {
    final r = parseAndValidate(
      '{"answer_indices":[0],"confidence":1.7}',
      _choice(QuestionType.singleChoice),
      provider: 'm',
    );
    expect(r.confidence, 1.0);
  });

  test('garbage throws InvalidAnswer', () {
    expect(
      () => parseAndValidate('not json', _text(), provider: 'm'),
      throwsA(isA<InvalidAnswer>()),
    );
  });

  test('extracts JSON from local-model preamble', () {
    final r = parseAndValidate(
      'Конечно! Вот ответ:\n{"answer_indices":[2],"confidence":0.7} — готово.',
      _choice(QuestionType.singleChoice),
      provider: 'local',
    );
    expect(r.answerIndices, [2]);
  });

  test('extractJsonObject handles nested braces and strings', () {
    final s = extractJsonObject(
      'blah {"answer_text":"a {b} c","confidence":0.5} trailing',
    );
    expect(s, '{"answer_text":"a {b} c","confidence":0.5}');
  });

  test('extractJsonObject returns null when no object', () {
    expect(extractJsonObject('no braces here'), isNull);
  });
}
