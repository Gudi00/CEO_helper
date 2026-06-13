import 'package:flutter_test/flutter_test.dart';
import 'package:google_form_app/ai/ai_client.dart';
import 'package:google_form_app/models/answer_result.dart';
import 'package:google_form_app/models/question.dart';
import 'package:google_form_app/settings/app_settings.dart';
import 'package:google_form_app/webview/form_controller.dart';

class _FakeAi implements AiClient {
  _FakeAi(this.result);
  final AnswerResult result;
  int calls = 0;
  final List<String> askedIds = [];

  @override
  Future<AnswerResult> answer(Question question) async {
    calls++;
    askedIds.add(question.id);
    return result;
  }
}

class _ThrowingAi implements AiClient {
  @override
  Future<AnswerResult> answer(Question question) async {
    throw AiException('boom');
  }
}

Map<String, dynamic> _rawChoice({String id = 'f:0'}) => {
      'id': id,
      'type': 'single_choice',
      'text': 'Choose',
      'options': [
        {'index': 0, 'value': 'a', 'text': 'alpha'},
        {'index': 1, 'value': 'b', 'text': 'beta'},
      ],
      'formId': 'f',
      'index': 0,
    };

/// Captures every JS snippet the controller asks the WebView to run and lets a
/// test wait until the queue has fully drained.
class _JsRecorder {
  final List<String> calls = [];
  Future<void> run(String js) async => calls.add(js);
}

void main() {
  const result = AnswerResult(
    answerIndices: [1],
    answerText: null,
    confidence: 0.9,
    reasoning: 'r',
    provider: 'm',
  );

  test('submit answers a question once and emits pending + apply JS', () async {
    final ai = _FakeAi(result);
    final rec = _JsRecorder();
    final c = FormController(
      aiClient: ai,
      applyMode: ApplyMode.autofill,
      runJs: rec.run,
    );

    c.submit([_rawChoice()]);
    await pumpUntilIdle();

    expect(ai.calls, 1);
    expect(rec.calls.any((j) => j.contains('pending(')), isTrue);
    final apply = rec.calls.firstWhere((j) => j.contains('apply('));
    expect(apply, contains('"answer_indices":[1]'));
    expect(apply, contains('"autofill"'));
  });

  test('re-submitting the same qid does not re-answer it', () async {
    final ai = _FakeAi(result);
    final rec = _JsRecorder();
    final c = FormController(
      aiClient: ai,
      applyMode: ApplyMode.suggest,
      runJs: rec.run,
    );

    c.submit([_rawChoice()]);
    await pumpUntilIdle();
    c.submit([_rawChoice()]); // same content arrives again from a re-parse
    await pumpUntilIdle();

    expect(ai.calls, 1);
  });

  test('questions are processed strictly one at a time, in order', () async {
    final ai = _FakeAi(result);
    final rec = _JsRecorder();
    final c = FormController(
      aiClient: ai,
      applyMode: ApplyMode.suggest,
      runJs: rec.run,
    );

    c.submit([
      _rawChoice(id: 'f:0'),
      _rawChoice(id: 'f:1'),
      _rawChoice(id: 'f:2'),
    ]);
    await pumpUntilIdle();

    expect(ai.askedIds, ['f:0', 'f:1', 'f:2']);
    // For each question: pending then apply, never interleaved.
    expect(
      rec.calls.where((j) => j.contains('pending(') || j.contains('apply(')).length,
      6,
    );
  });

  test('AI failure clears the pending marker and surfaces the error', () async {
    final rec = _JsRecorder();
    final c = FormController(
      aiClient: _ThrowingAi(),
      applyMode: ApplyMode.suggest,
      runJs: rec.run,
    );

    c.submit([_rawChoice()]);
    await pumpUntilIdle();

    expect(c.status.value, contains('Ошибка AI'));
    expect(rec.calls.any((j) => j.contains('clearPending(')), isTrue);
    expect(rec.calls.any((j) => j.contains('apply(')), isFalse);
  });
}

/// The queue drains on microtasks/timers; let them all run.
Future<void> pumpUntilIdle() =>
    Future<void>.delayed(const Duration(milliseconds: 10));
