import '../models/answer_result.dart';
import '../models/question.dart';
import 'ai_client.dart';
import 'answer_parser.dart';
import 'local_engine.dart';
import 'prompts.dart';

/// [AiClient] backed by an on-device model (flutter_gemma). Same JSON contract
/// and prompts as [GeminiClient]; the only difference is where inference runs.
class LocalLlmClient implements AiClient {
  LocalLlmClient({
    required this.modelLabel,
    this.customSystemPrompt,
    this.targetLanguage,
    LocalEngine? engine,
  }) : _engine = engine ?? LocalEngine.instance;

  final String modelLabel;
  final String? customSystemPrompt;
  final String? targetLanguage;
  final LocalEngine _engine;

  @override
  Future<AnswerResult> answer(Question question) async {
    if (!_engine.isReady) {
      throw AiException(
        'Локальная модель не загружена. Откройте «Настройки» → загрузите модель.',
      );
    }
    final system = buildSystemPrompt(
      custom: customSystemPrompt,
      targetLanguage: targetLanguage,
    );
    final user = renderUserPrompt(question);

    final String raw;
    try {
      raw = await _engine.generate(system: system, user: user);
    } catch (e) {
      throw AiException('Локальная модель: $e');
    }
    if (raw.trim().isEmpty) {
      throw AiException('Локальная модель вернула пустой ответ.');
    }
    return parseAndValidate(raw, question, provider: 'local:$modelLabel');
  }
}
