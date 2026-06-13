import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../ai/ai_client.dart';
import '../models/answer_result.dart';
import '../models/question.dart';
import '../settings/app_settings.dart';

/// Drives answering. Parsed questions are pushed in via [submit] and processed
/// **strictly one at a time** through a FIFO queue (same single-question flow as
/// the iis.bsuir bot): each question gets a "thinking" marker, is re-solved from
/// scratch by the AI (no caching — always a fresh answer), then its answer is
/// applied before the next question starts. This avoids work "jumping" between
/// questions and the mutation-observer feedback loop that re-fired endlessly.
class FormController {
  FormController({
    required this.aiClient,
    required this.applyMode,
    required this.runJs,
  });

  final AiClient aiClient;
  final ApplyMode applyMode;

  /// Runs a JS snippet inside the WebView. Injected by the screen so the
  /// controller can sequence pending/apply calls itself.
  final Future<void> Function(String js) runJs;

  /// qids already enqueued this session, so MutationObserver re-pushes and
  /// duplicate parses are no-ops (a question is handled exactly once).
  final Set<String> _seen = {};
  final List<Map<String, dynamic>> _queue = [];
  bool _draining = false;

  /// Status messages for the UI (last action / errors).
  final ValueNotifier<String> status = ValueNotifier('Откройте форму.');

  /// Enqueue a freshly-parsed batch of questions. New (unseen) questions are
  /// appended to the queue and the single drain loop picks them up in order.
  void submit(List<Map<String, dynamic>> raws) {
    for (final raw in raws) {
      final id = raw['id'] as String?;
      if (id == null || _seen.contains(id)) continue;
      _seen.add(id);
      _queue.add(raw);
    }
    _drain();
  }

  /// Process the queue one question at a time. Guarded so only a single loop
  /// runs even if [submit] is called repeatedly while answering.
  Future<void> _drain() async {
    if (_draining) return;
    _draining = true;
    try {
      while (_queue.isNotEmpty) {
        await _handle(_queue.removeAt(0));
      }
    } finally {
      _draining = false;
    }
  }

  Future<void> _handle(Map<String, dynamic> raw) async {
    final q = Question.fromJson(raw);
    final qidJson = jsonEncode(q.id);
    status.value = '🤖 Отвечаю на вопрос ${q.index + 1}…';
    await runJs('window.__gfa&&window.__gfa.pending($qidJson);');

    final AnswerResult result;
    try {
      result = await aiClient.answer(q);
    } on AiException catch (e) {
      status.value = 'Ошибка AI: ${e.message}';
      await runJs('window.__gfa&&window.__gfa.clearPending($qidJson);');
      return;
    }

    status.value =
        'Готово: вопрос ${q.index + 1} (${(result.confidence * 100).round()}%)';
    await runJs(_applyJs(q.id, result));
  }

  String _applyJs(String qid, AnswerResult result) {
    final resultJson = jsonEncode(result.toJson());
    final qidJson = jsonEncode(qid);
    final modeJson = jsonEncode(applyMode.wire);
    return 'window.__gfa && window.__gfa.apply($qidJson, $resultJson, $modeJson);';
  }
}
