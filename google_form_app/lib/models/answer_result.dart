/// The model's decision for one question.
///
/// For choice questions [answerIndices] is filled and [answerText] is null.
/// For text questions [answerText] is filled and [answerIndices] is empty.
class AnswerResult {
  const AnswerResult({
    required this.answerIndices,
    required this.answerText,
    required this.confidence,
    required this.reasoning,
    required this.provider,
    this.fromCache = false,
  });

  final List<int> answerIndices;
  final String? answerText;

  /// 0..1 self-rated certainty.
  final double confidence;
  final String? reasoning;

  /// Model id that produced the answer (or 'cache').
  final String provider;
  final bool fromCache;

  AnswerResult copyWith({double? confidence, bool? fromCache, String? provider}) {
    return AnswerResult(
      answerIndices: answerIndices,
      answerText: answerText,
      confidence: confidence ?? this.confidence,
      reasoning: reasoning,
      provider: provider ?? this.provider,
      fromCache: fromCache ?? this.fromCache,
    );
  }

  factory AnswerResult.fromJson(Map<String, dynamic> json) => AnswerResult(
        answerIndices: ((json['answer_indices'] ?? const []) as List)
            .map((e) => (e as num).toInt())
            .toList(),
        answerText: json['answer_text'] as String?,
        confidence: ((json['confidence'] ?? 0) as num).toDouble(),
        reasoning: json['reasoning'] as String?,
        provider: (json['provider'] ?? '') as String,
        fromCache: (json['from_cache'] ?? false) as bool,
      );

  Map<String, dynamic> toJson() => {
        'answer_indices': answerIndices,
        'answer_text': answerText,
        'confidence': confidence,
        'reasoning': reasoning,
        'provider': provider,
        'from_cache': fromCache,
      };
}
