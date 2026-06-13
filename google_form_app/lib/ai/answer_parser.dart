import 'dart:convert';

import '../models/answer_result.dart';
import '../models/question.dart';
import '../models/question_type.dart';

/// Thrown when the model's reply cannot be turned into a valid [AnswerResult].
class InvalidAnswer implements Exception {
  InvalidAnswer(this.message);
  final String message;
  @override
  String toString() => 'InvalidAnswer: $message';
}

/// Parse + validate Gemini's JSON reply against the question it answers.
///
/// Ported from `_parse_and_validate` in the original `backend/src/ai/gemini.py`,
/// extended to handle [QuestionType.textInput].
AnswerResult parseAndValidate(
  String rawText,
  Question question, {
  required String provider,
}) {
  final jsonStr = extractJsonObject(_stripFences(rawText)) ?? _stripFences(rawText);
  final Map<String, dynamic> data;
  try {
    final decoded = json.decode(jsonStr);
    if (decoded is! Map<String, dynamic>) {
      throw InvalidAnswer('Reply is not a JSON object: ${_clip(rawText)}');
    }
    data = decoded;
  } on FormatException catch (e) {
    throw InvalidAnswer('Bad JSON from model: ${_clip(rawText)} ($e)');
  }

  final indices = ((data['answer_indices'] ?? const []) as List)
      .map((e) => (e as num).toInt())
      .toList();
  final text = (data['answer_text'] as String?)?.trim();
  final double confidence =
      ((data['confidence'] ?? 0) as num).toDouble().clamp(0.0, 1.0).toDouble();
  final reasoning = data['reasoning'] as String?;

  if (question.type == QuestionType.textInput) {
    if (text == null || text.isEmpty) {
      throw InvalidAnswer('Empty answer_text for text question ${question.id}');
    }
    return AnswerResult(
      answerIndices: const [],
      answerText: text,
      confidence: confidence,
      reasoning: reasoning,
      provider: provider,
    );
  }

  // Choice question: validate index range.
  final maxIndex = question.options.length - 1;
  if (indices.isEmpty || indices.any((i) => i < 0 || i > maxIndex)) {
    throw InvalidAnswer(
      'indices out of range: $indices (max $maxIndex) for ${question.id}',
    );
  }

  // single_choice must yield exactly one index; if more, keep the first and
  // discount confidence (same heuristic as the original backend).
  if (question.type == QuestionType.singleChoice && indices.length != 1) {
    return AnswerResult(
      answerIndices: [indices.first],
      answerText: null,
      confidence: confidence * 0.7,
      reasoning: reasoning,
      provider: provider,
    );
  }

  return AnswerResult(
    answerIndices: indices,
    answerText: null,
    confidence: confidence,
    reasoning: reasoning,
    provider: provider,
  );
}

/// Pull the first balanced `{...}` object out of arbitrary text. Local models
/// often prepend reasoning / preamble before the JSON despite instructions;
/// this finds the object regardless. Returns null if no balanced object found.
String? extractJsonObject(String s) {
  final start = s.indexOf('{');
  if (start < 0) return null;
  var depth = 0;
  var inStr = false;
  var esc = false;
  for (var i = start; i < s.length; i++) {
    final c = s[i];
    if (inStr) {
      if (esc) {
        esc = false;
      } else if (c == r'\') {
        esc = true;
      } else if (c == '"') {
        inStr = false;
      }
    } else if (c == '"') {
      inStr = true;
    } else if (c == '{') {
      depth++;
    } else if (c == '}') {
      depth--;
      if (depth == 0) return s.substring(start, i + 1);
    }
  }
  return null;
}

/// Defensive: some models still wrap JSON in ```json fences despite the prompt.
String _stripFences(String s) {
  var t = s.trim();
  if (t.startsWith('```')) {
    t = t.replaceFirst(RegExp(r'^```[a-zA-Z]*\s*'), '');
    if (t.endsWith('```')) t = t.substring(0, t.length - 3);
  }
  return t.trim();
}

String _clip(String s) => s.length <= 120 ? s : '${s.substring(0, 120)}…';
