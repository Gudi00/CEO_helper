import '../ai/local_engine.dart' show LocalBackend;

export '../ai/local_engine.dart' show LocalBackend;

/// Which backend answers questions.
enum AiProvider {
  /// Cloud Gemini via REST (needs an API key).
  gemini('gemini'),

  /// On-device model via flutter_gemma (no key; downloads a model once).
  local('local');

  const AiProvider(this.wire);
  final String wire;

  static AiProvider fromWire(String? v) =>
      AiProvider.values.firstWhere((p) => p.wire == v,
          orElse: () => AiProvider.gemini);
}

/// How the app applies the model's answer to the live form.
enum ApplyMode {
  /// Only highlight / show the suggested answer; user acts.
  suggest('suggest'),

  /// Fill radio/checkbox/text automatically (but never submit).
  autofill('autofill');

  const ApplyMode(this.wire);
  final String wire;

  static ApplyMode fromWire(String? v) =>
      ApplyMode.values.firstWhere((m) => m.wire == v,
          orElse: () => ApplyMode.suggest);
}

/// User-tunable settings. The API key lives in secure storage; everything here
/// is non-secret and stored in SharedPreferences.
class AppSettings {
  const AppSettings({
    this.provider = AiProvider.gemini,
    this.model = defaultModel,
    this.localModelId = defaultLocalModelId,
    this.localBackend = LocalBackend.cpu,
    this.applyMode = ApplyMode.suggest,
    this.targetLanguage = '',
    this.customSystemPrompt = '',
  });

  /// Default on-device model preset id (see local_models.dart).
  static const String defaultLocalModelId = 'gemma4_e2b';

  /// Capable multilingual default. Editable in the UI — recheck current ids in
  /// the Gemini docs; a "pro" model gives best results on hard language tests.
  static const String defaultModel = 'gemini-2.5-flash';

  static const List<String> modelPresets = [
    'gemini-2.5-flash',
    'gemini-2.5-pro',
    'gemini-2.0-flash',
  ];

  final AiProvider provider;
  final String model;

  /// Selected on-device model preset id.
  final String localModelId;

  /// On-device inference backend (CPU is the most compatible).
  final LocalBackend localBackend;

  final ApplyMode applyMode;

  /// Optional hint (e.g. "английский") added to the system prompt.
  final String targetLanguage;

  /// Optional override of the default expert role.
  final String customSystemPrompt;

  AppSettings copyWith({
    AiProvider? provider,
    String? model,
    String? localModelId,
    LocalBackend? localBackend,
    ApplyMode? applyMode,
    String? targetLanguage,
    String? customSystemPrompt,
  }) {
    return AppSettings(
      provider: provider ?? this.provider,
      model: model ?? this.model,
      localModelId: localModelId ?? this.localModelId,
      localBackend: localBackend ?? this.localBackend,
      applyMode: applyMode ?? this.applyMode,
      targetLanguage: targetLanguage ?? this.targetLanguage,
      customSystemPrompt: customSystemPrompt ?? this.customSystemPrompt,
    );
  }
}
