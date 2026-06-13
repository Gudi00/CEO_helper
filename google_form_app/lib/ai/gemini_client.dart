import 'package:dio/dio.dart';

import '../models/answer_result.dart';
import '../models/question.dart';
import 'ai_client.dart';
import 'answer_parser.dart';
import 'prompts.dart';

/// Calls the Gemini `generateContent` REST endpoint directly from the device.
///
/// No backend server is involved: the user's API key is sent device→Google.
/// Config mirrors the original `backend/src/ai/gemini.py` (low temperature,
/// JSON response mime type, system instruction).
class GeminiClient implements AiClient {
  GeminiClient({
    required this.apiKey,
    required this.model,
    this.customSystemPrompt,
    this.targetLanguage,
    this.timeout = const Duration(seconds: 20),
    Dio? dio,
  }) : _dio = dio ?? Dio();

  static const String _base =
      'https://generativelanguage.googleapis.com/v1beta/models';

  final String apiKey;
  final String model;
  final String? customSystemPrompt;
  final String? targetLanguage;
  final Duration timeout;
  final Dio _dio;

  @override
  Future<AnswerResult> answer(Question question) async {
    if (apiKey.isEmpty) {
      throw AiException('Не задан API-ключ Gemini (см. настройки).');
    }

    final systemPrompt = buildSystemPrompt(
      custom: customSystemPrompt,
      targetLanguage: targetLanguage,
    );
    final body = {
      'systemInstruction': {
        'parts': [
          {'text': systemPrompt}
        ]
      },
      'contents': [
        {
          'role': 'user',
          'parts': [
            {'text': renderUserPrompt(question)}
          ]
        }
      ],
      'generationConfig': {
        // Low temperature keeps answers factual (minimal hallucination) while
        // leaving just enough room to settle on a well-formed reply.
        'temperature': 0.2,
        'topP': 0.95,
        'maxOutputTokens': 1024,
        'responseMimeType': 'application/json',
      },
    };

    final Response<dynamic> resp;
    try {
      resp = await _dio.post<dynamic>(
        '$_base/$model:generateContent',
        queryParameters: {'key': apiKey},
        data: body,
        options: Options(
          sendTimeout: timeout,
          receiveTimeout: timeout,
          contentType: 'application/json',
          // We classify non-2xx ourselves to give a useful message.
          validateStatus: (_) => true,
        ),
      );
    } on DioException catch (e) {
      throw AiException('Сеть/таймаут Gemini: ${e.message}');
    }

    final status = resp.statusCode ?? 0;
    if (status == 429) {
      throw AiException('Превышена квота Gemini (429).', isQuota: true);
    }
    if (status < 200 || status >= 300) {
      throw AiException('Gemini вернул $status: ${_errText(resp.data)}');
    }

    final raw = _extractText(resp.data);
    if (raw.trim().isEmpty) {
      throw AiException('Gemini вернул пустой ответ.');
    }
    return parseAndValidate(raw, question, provider: model);
  }

  /// Pull the text out of `candidates[0].content.parts[*].text`.
  String _extractText(dynamic data) {
    try {
      final candidates = data['candidates'] as List;
      final parts = candidates.first['content']['parts'] as List;
      return parts.map((p) => (p['text'] ?? '') as String).join();
    } catch (_) {
      throw AiException('Неожиданная структура ответа Gemini: ${_clip(data)}');
    }
  }

  String _errText(dynamic data) {
    try {
      return (data['error']?['message'] ?? data).toString();
    } catch (_) {
      return data.toString();
    }
  }

  String _clip(dynamic data) {
    final s = data.toString();
    return s.length <= 200 ? s : '${s.substring(0, 200)}…';
  }
}
