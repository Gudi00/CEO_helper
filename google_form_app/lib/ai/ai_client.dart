import '../models/answer_result.dart';
import '../models/question.dart';

/// Abstraction over the answering backend. Today only Gemini is implemented;
/// the interface keeps room for adding e.g. OpenAI later without touching the
/// WebView/UI layers.
abstract class AiClient {
  Future<AnswerResult> answer(Question question);
}

/// Raised for any failure talking to the provider (network, quota, bad reply).
class AiException implements Exception {
  AiException(this.message, {this.isQuota = false});
  final String message;
  final bool isQuota;
  @override
  String toString() => 'AiException: $message';
}
