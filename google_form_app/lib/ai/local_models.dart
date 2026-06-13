import 'package:flutter_gemma/flutter_gemma.dart';

/// A downloadable on-device model preset. All defaults here are **token-free**
/// (`needsAuth: false`) so users without any API key can use the app; a HF
/// token is only needed if you add a gated model later.
class LocalModelPreset {
  const LocalModelPreset({
    required this.id,
    required this.displayName,
    required this.url,
    required this.filename,
    required this.sizeLabel,
    required this.modelType,
    required this.fileType,
    this.needsAuth = false,
    this.note = '',
  });

  final String id;
  final String displayName;
  final String url;
  final String filename;
  final String sizeLabel;
  final ModelType modelType;
  final ModelFileType fileType;
  final bool needsAuth;
  final String note;
}

/// Registry of offered models. URLs/specs taken from the flutter_gemma model
/// catalog (litert-community builds are openly downloadable — no token).
const List<LocalModelPreset> kLocalPresets = [
  LocalModelPreset(
    id: 'gemma4_e2b',
    displayName: 'Gemma 4 E2B (рекомендуется)',
    url: 'https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/'
        'resolve/main/gemma-4-E2B-it.litertlm',
    filename: 'gemma-4-E2B-it.litertlm',
    sizeLabel: '2.4 GB',
    modelType: ModelType.gemma4,
    fileType: ModelFileType.litertlm,
    note: 'Свежая мультиязычная модель Google. Без токена. '
        'Подходит для большинства современных телефонов.',
  ),
  LocalModelPreset(
    id: 'gemma4_e4b',
    displayName: 'Gemma 4 E4B (лучше качество)',
    url: 'https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/'
        'resolve/main/gemma-4-E4B-it.litertlm',
    filename: 'gemma-4-E4B-it.litertlm',
    sizeLabel: '4.3 GB',
    modelType: ModelType.gemma4,
    fileType: ModelFileType.litertlm,
    note: 'Точнее, но тяжелее. Нужен мощный телефон (≥8 ГБ ОЗУ).',
  ),
  LocalModelPreset(
    id: 'qwen25_1_5b',
    displayName: 'Qwen2.5 1.5B (лёгкая)',
    url: 'https://huggingface.co/litert-community/Qwen2.5-1.5B-Instruct/'
        'resolve/main/Qwen2.5-1.5B-Instruct_multi-prefill-seq_q8_ekv4096.litertlm',
    filename: 'Qwen2.5-1.5B-Instruct_multi-prefill-seq_q8_ekv4096.litertlm',
    sizeLabel: '1.6 GB',
    modelType: ModelType.qwen,
    fileType: ModelFileType.litertlm,
    note: 'Самая лёгкая и быстрая, мультиязычная. Качество ниже Gemma 4.',
  ),
];

LocalModelPreset presetById(String? id) => kLocalPresets.firstWhere(
      (p) => p.id == id,
      orElse: () => kLocalPresets.first,
    );
