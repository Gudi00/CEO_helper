import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../models/question_type.dart';

/// Stable SHA-256 hash of a question's *identity*.
///
/// Order-independent over options (sorted before hashing) and tolerant of
/// whitespace/case, so the same question caches across attempts even when the
/// form randomizes option order. Ported from the original project's
/// `backend/src/moodle/hashing.py` / `extension/src/shared/hash.ts`.
String computeQuestionHash(
  String text,
  QuestionType type,
  List<String> optionTexts,
) {
  final normalizedText = _normalize(text);
  final normalizedOptions = optionTexts.map(_normalize).toList()..sort();
  final payload = [
    normalizedText,
    type.wire,
    normalizedOptions.join('|'),
  ].join('\n');
  return sha256.convert(utf8.encode(payload)).toString();
}

String _normalize(String s) {
  return s.trim().toLowerCase().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).join(' ');
}
