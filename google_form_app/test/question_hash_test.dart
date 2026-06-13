import 'package:flutter_test/flutter_test.dart';
import 'package:google_form_app/models/question_type.dart';
import 'package:google_form_app/util/question_hash.dart';

void main() {
  test('hash is stable regardless of option order', () {
    final a = computeQuestionHash(
      'What is 2+2?',
      QuestionType.singleChoice,
      ['three', 'four', 'five'],
    );
    final b = computeQuestionHash(
      'What is 2+2?',
      QuestionType.singleChoice,
      ['five', 'four', 'three'],
    );
    expect(a, b);
  });

  test('hash ignores case and surrounding whitespace', () {
    final a = computeQuestionHash('Hello   World', QuestionType.textInput, []);
    final b = computeQuestionHash('  hello world ', QuestionType.textInput, []);
    expect(a, b);
  });

  test('different type changes hash', () {
    final a = computeQuestionHash('q', QuestionType.singleChoice, ['x', 'y']);
    final b = computeQuestionHash('q', QuestionType.multipleChoice, ['x', 'y']);
    expect(a, isNot(b));
  });

  test('produces 64-char hex', () {
    final h = computeQuestionHash('q', QuestionType.textInput, []);
    expect(h, matches(RegExp(r'^[0-9a-f]{64}$')));
  });
}
