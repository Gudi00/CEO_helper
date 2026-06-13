import 'package:flutter_test/flutter_test.dart';
import 'package:google_form_app/ai/prompts.dart';
import 'package:google_form_app/models/question.dart';
import 'package:google_form_app/models/question_type.dart';

void main() {
  test('system prompt always carries the JSON instruction', () {
    final p = buildSystemPrompt();
    expect(p, contains('answer_indices'));
    expect(p, contains('answer_text'));
  });

  test('custom role overrides default but keeps JSON block', () {
    final p = buildSystemPrompt(custom: 'Ты — математик.');
    expect(p, contains('Ты — математик.'));
    expect(p, isNot(contains('филолог')));
    expect(p, contains('JSON'));
  });

  test('target language hint is injected when set', () {
    final p = buildSystemPrompt(targetLanguage: 'английский');
    expect(p, contains('английский'));
  });

  test('choice user prompt lists 0-based options', () {
    const q = Question(
      id: 'f:0',
      hash: '',
      type: QuestionType.singleChoice,
      text: 'Choose',
      options: [
        Option(index: 0, value: 'a', text: 'alpha'),
        Option(index: 1, value: 'b', text: 'beta'),
      ],
      formId: 'f',
      index: 0,
    );
    final p = renderUserPrompt(q);
    expect(p, contains('0) alpha'));
    expect(p, contains('1) beta'));
  });

  test('text user prompt asks for written answer', () {
    const q = Question(
      id: 'f:1',
      hash: '',
      type: QuestionType.textInput,
      text: 'Translate "house"',
      options: [],
      formId: 'f',
      index: 1,
    );
    final p = renderUserPrompt(q);
    expect(p, contains('answer_text'));
    expect(p, contains('Translate "house"'));
  });
}
