import 'question_type.dart';

/// One selectable option of a choice question.
class Option {
  const Option({required this.index, required this.value, required this.text});

  /// 0-based position of the option in the form.
  final int index;

  /// The form's internal value (Google's `data-value` / aria text). May equal
  /// [text]; kept separate so we can match the DOM element back precisely.
  final String value;

  /// Human-readable option text.
  final String text;

  factory Option.fromJson(Map<String, dynamic> json) => Option(
        index: json['index'] as int,
        value: (json['value'] ?? '') as String,
        text: json['text'] as String,
      );

  Map<String, dynamic> toJson() => {
        'index': index,
        'value': value,
        'text': text,
      };
}

/// A normalized question, independent of the platform it was parsed from.
///
/// Mirrors the `NormalizedQuestion` contract of the original Moodle project
/// (`extension/src/shared/types.ts`), extended with [QuestionType.textInput].
class Question {
  const Question({
    required this.id,
    required this.hash,
    required this.type,
    required this.text,
    required this.options,
    required this.formId,
    required this.index,
    this.hasImages = false,
  });

  /// Stable DOM id used to map answers back to the element (`data-gfa-qid`).
  final String id;

  /// Content hash (see `question_hash.dart`) — used for cache/history dedupe.
  final String hash;

  final QuestionType type;
  final String text;

  /// Empty for [QuestionType.textInput].
  final List<Option> options;

  /// Google Forms form id (parsed from the URL).
  final String formId;

  /// 0-based order of this question within the form.
  final int index;

  final bool hasImages;

  factory Question.fromJson(Map<String, dynamic> json) => Question(
        id: json['id'] as String,
        hash: (json['hash'] ?? '') as String,
        type: QuestionType.fromWire(json['type'] as String),
        text: json['text'] as String,
        options: ((json['options'] ?? const []) as List)
            .map((o) => Option.fromJson(o as Map<String, dynamic>))
            .toList(),
        formId: (json['formId'] ?? json['form_id'] ?? '') as String,
        index: (json['index'] ?? 0) as int,
        hasImages: (json['hasImages'] ?? json['has_images'] ?? false) as bool,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'hash': hash,
        'type': type.wire,
        'text': text,
        'options': options.map((o) => o.toJson()).toList(),
        'formId': formId,
        'index': index,
        'hasImages': hasImages,
      };
}
