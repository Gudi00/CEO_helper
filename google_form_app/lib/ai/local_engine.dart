import 'dart:async';

import 'package:flutter_gemma/flutter_gemma.dart';

import 'local_models.dart';

/// Backend selection for on-device inference.
enum LocalBackend {
  /// Let the plugin decide.
  auto('auto', null),

  /// CPU — slowest but the most compatible/stable across devices.
  cpu('cpu', PreferredBackend.cpu),

  /// GPU — faster, but may fail to initialise on some devices.
  gpu('gpu', PreferredBackend.gpu);

  const LocalBackend(this.wire, this.pref);
  final String wire;
  final PreferredBackend? pref;

  static LocalBackend fromWire(String? v) =>
      LocalBackend.values.firstWhere((b) => b.wire == v,
          orElse: () => LocalBackend.cpu);
}

/// Singleton owning on-device model lifecycle: download/install, load, and
/// one-shot generation. Shared between settings (install) and the form (use).
///
/// Inference is **serialized** — concurrent `createSession` calls crash the
/// native MediaPipe/LiteRT engine ("Failed to start streaming (code: -1)").
class LocalEngine {
  LocalEngine._();
  static final LocalEngine instance = LocalEngine._();

  InferenceModel? _model;
  bool _initialized = false;
  Future<void> _lock = Future.value();

  LocalBackend backend = LocalBackend.cpu;
  int maxTokens = 1024;

  /// Preset id of the model currently active in memory (null if none).
  String? activePresetId;

  Future<void> _ensureInit({String? hfToken}) async {
    if (_initialized) return;
    await FlutterGemma.initialize(
      huggingFaceToken: (hfToken != null && hfToken.isNotEmpty) ? hfToken : null,
    );
    _initialized = true;
  }

  /// True once a model is loaded in memory and ready for inference.
  bool get isReady => FlutterGemma.hasActiveModel() && activePresetId != null;

  /// Whether the preset's file is already downloaded on the device.
  Future<bool> isDownloaded(LocalModelPreset preset) async {
    try {
      await _ensureInit();
      return await FlutterGemma.isModelInstalled(preset.filename);
    } catch (_) {
      return false;
    }
  }

  /// Download (if needed) and activate [preset]. Idempotent: if the file is
  /// already present the download step is skipped and the model is just
  /// (re)activated. [onProgress] reports 0..100.
  Future<void> install(
    LocalModelPreset preset, {
    String? token,
    void Function(int progress)? onProgress,
  }) async {
    await _ensureInit(hfToken: token);
    await FlutterGemma.installModel(
      modelType: preset.modelType,
      fileType: preset.fileType,
    )
        .fromNetwork(
          preset.url,
          token: (preset.needsAuth && token != null && token.isNotEmpty)
              ? token
              : null,
        )
        .withProgress((p) => onProgress?.call(p))
        .install();
    await _disposeModel();
    activePresetId = preset.id;
  }

  Future<void> _disposeModel() async {
    final m = _model;
    _model = null;
    if (m != null) {
      try {
        await m.close();
      } catch (_) {/* best effort */}
    }
  }

  Future<InferenceModel> _ensureModel() async {
    if (!FlutterGemma.hasActiveModel()) {
      throw StateError(
        'Локальная модель не загружена. Откройте «Настройки» и нажмите '
        '«Загрузить в память».',
      );
    }
    return _model ??= await FlutterGemma.getActiveModel(
      maxTokens: maxTokens,
      preferredBackend: backend.pref,
    );
  }

  /// One-shot generation, serialized and self-healing: a fresh session per
  /// call (no context bleed), and on any native failure the model is disposed
  /// so the next call rebuilds a clean engine.
  Future<String> generate({
    required String system,
    required String user,
  }) {
    return _serialized(() async {
      final model = await _ensureModel();
      InferenceModelSession? session;
      try {
        session = await model.createSession(
          // Low temperature → factual answers, minimal hallucination.
          temperature: 0.2,
          topK: 40,
          topP: 0.95,
          systemInstruction: system,
          enableThinking: false,
        );
        await session.addQueryChunk(Message.text(text: user, isUser: true));
        return await session.getResponse();
      } catch (e) {
        // Native engine likely in a bad state — drop the model so the next
        // question reloads it fresh.
        await _disposeModel();
        rethrow;
      } finally {
        try {
          await session?.close();
        } catch (_) {/* best effort */}
      }
    });
  }

  /// Run [fn] after any in-flight inference completes.
  Future<T> _serialized<T>(Future<T> Function() fn) async {
    final prev = _lock;
    final done = Completer<void>();
    _lock = done.future;
    try {
      await prev;
      return await fn();
    } finally {
      done.complete();
    }
  }
}
