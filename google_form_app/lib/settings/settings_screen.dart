import 'package:flutter/material.dart';

import '../ai/local_engine.dart';
import '../ai/local_models.dart';
import 'app_settings.dart';
import 'settings_repository.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.repo});

  final SettingsRepository repo;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _apiKey;
  late final TextEditingController _hfToken;
  late final TextEditingController _model;
  late final TextEditingController _lang;
  late final TextEditingController _prompt;
  late AiProvider _provider;
  late ApplyMode _mode;
  late String _localModelId;
  late LocalBackend _backend;

  bool _downloading = false;
  int _progress = 0;
  bool _downloaded = false; // selected preset already on device?
  String _downloadStatus = '';

  @override
  void initState() {
    super.initState();
    final s = widget.repo.settings.value;
    _apiKey = TextEditingController(text: widget.repo.apiKey);
    _hfToken = TextEditingController(text: widget.repo.hfToken);
    _model = TextEditingController(text: s.model);
    _lang = TextEditingController(text: s.targetLanguage);
    _prompt = TextEditingController(text: s.customSystemPrompt);
    _provider = s.provider;
    _mode = s.applyMode;
    _localModelId = s.localModelId;
    _backend = s.localBackend;
    _refreshDownloaded();
  }

  Future<void> _refreshDownloaded() async {
    final preset = presetById(_localModelId);
    final downloaded = await LocalEngine.instance.isDownloaded(preset);
    if (!mounted) return;
    setState(() {
      _downloaded = downloaded;
      _downloadStatus = _statusFor(preset, downloaded);
    });
  }

  String _statusFor(LocalModelPreset preset, bool downloaded) {
    final active = LocalEngine.instance.isReady &&
        LocalEngine.instance.activePresetId == preset.id;
    if (active) return '✅ Активна и готова отвечать.';
    if (downloaded) return '⬇️ Скачана. Нажмите «Загрузить в память».';
    return 'Не скачана.';
  }

  Future<void> _save() async {
    await widget.repo.saveApiKey(_apiKey.text);
    await widget.repo.saveHfToken(_hfToken.text);
    await widget.repo.save(
      AppSettings(
        provider: _provider,
        model: _model.text.trim().isEmpty
            ? AppSettings.defaultModel
            : _model.text.trim(),
        localModelId: _localModelId,
        localBackend: _backend,
        applyMode: _mode,
        targetLanguage: _lang.text.trim(),
        customSystemPrompt: _prompt.text.trim(),
      ),
    );
    LocalEngine.instance.backend = _backend;
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('✅ Настройки сохранены')),
      );
      Navigator.pop(context);
    }
  }

  Future<void> _downloadModel() async {
    final preset = presetById(_localModelId);
    LocalEngine.instance.backend = _backend;
    setState(() {
      _downloading = true;
      _progress = 0;
      _downloadStatus = _downloaded
          ? 'Загрузка ${preset.displayName} в память…'
          : 'Скачивание ${preset.displayName}…';
    });
    try {
      await LocalEngine.instance.install(
        preset,
        token: _hfToken.text.trim(),
        onProgress: (p) {
          if (mounted) setState(() => _progress = p);
        },
      );
      if (!mounted) return;
      setState(() {
        _downloaded = true;
        _downloadStatus = '✅ ${preset.displayName} активна.';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('✅ Модель «${preset.displayName}» готова')),
      );
    } catch (e) {
      if (mounted) setState(() => _downloadStatus = '❌ Ошибка: $e');
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Настройки')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Источник ответов',
              style: TextStyle(fontWeight: FontWeight.bold)),
          RadioGroup<AiProvider>(
            groupValue: _provider,
            onChanged: (v) => setState(() => _provider = v!),
            child: const Column(
              children: [
                RadioListTile<AiProvider>(
                  value: AiProvider.gemini,
                  title: Text('Gemini (нужен API-ключ, точнее)'),
                ),
                RadioListTile<AiProvider>(
                  value: AiProvider.local,
                  title: Text('Локальная модель (на устройстве, без ключа)'),
                ),
              ],
            ),
          ),
          const Divider(height: 24),
          if (_provider == AiProvider.gemini) ..._geminiSection(),
          if (_provider == AiProvider.local) ..._localSection(),
          const Divider(height: 24),
          ..._commonSection(),
          const SizedBox(height: 24),
          FilledButton(onPressed: _save, child: const Text('Сохранить')),
        ],
      ),
    );
  }

  List<Widget> _geminiSection() => [
        TextField(
          controller: _apiKey,
          obscureText: true,
          decoration: const InputDecoration(
            labelText: 'API-ключ Gemini',
            border: OutlineInputBorder(),
            helperText: 'Хранится в защищённом хранилище устройства.',
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _model,
          decoration: const InputDecoration(
            labelText: 'Модель Gemini',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: AppSettings.modelPresets
              .map((m) => ActionChip(
                    label: Text(m),
                    onPressed: () => setState(() => _model.text = m),
                  ))
              .toList(),
        ),
      ];

  List<Widget> _localSection() {
    final preset = presetById(_localModelId);
    final active = LocalEngine.instance.isReady &&
        LocalEngine.instance.activePresetId == preset.id;
    return [
      Row(
        children: [
          const Text('Локальная модель'),
          const Spacer(),
          if (active)
            const Chip(
              label: Text('Активна'),
              avatar: Icon(Icons.check_circle, color: Colors.green, size: 18),
              visualDensity: VisualDensity.compact,
            )
          else if (_downloaded)
            const Chip(
              label: Text('Скачана'),
              avatar: Icon(Icons.download_done, size: 18),
              visualDensity: VisualDensity.compact,
            ),
        ],
      ),
      const SizedBox(height: 8),
      DropdownButtonFormField<String>(
        initialValue: _localModelId,
        isExpanded: true,
        decoration: const InputDecoration(border: OutlineInputBorder()),
        items: kLocalPresets
            .map((p) => DropdownMenuItem(
                  value: p.id,
                  child: Text('${p.displayName} · ${p.sizeLabel}'),
                ))
            .toList(),
        onChanged: _downloading
            ? null
            : (v) {
                setState(() =>
                    _localModelId = v ?? AppSettings.defaultLocalModelId);
                _refreshDownloaded();
              },
      ),
      const SizedBox(height: 8),
      Text(preset.note,
          style: const TextStyle(fontSize: 12, color: Colors.grey)),
      const SizedBox(height: 12),
      DropdownButtonFormField<LocalBackend>(
        initialValue: _backend,
        decoration: const InputDecoration(
          labelText: 'Движок инференса',
          border: OutlineInputBorder(),
          helperText: 'CPU — стабильнее, GPU — быстрее (может не работать).',
        ),
        items: const [
          DropdownMenuItem(value: LocalBackend.cpu, child: Text('CPU (надёжно)')),
          DropdownMenuItem(value: LocalBackend.gpu, child: Text('GPU (быстро)')),
          DropdownMenuItem(value: LocalBackend.auto, child: Text('Авто')),
        ],
        onChanged: _downloading
            ? null
            : (v) => setState(() => _backend = v ?? LocalBackend.cpu),
      ),
      if (preset.needsAuth) ...[
        const SizedBox(height: 12),
        TextField(
          controller: _hfToken,
          obscureText: true,
          decoration: const InputDecoration(
            labelText: 'HuggingFace токен (для этой модели)',
            border: OutlineInputBorder(),
            helperText: 'Бесплатный токен с huggingface.co/settings/tokens.',
          ),
        ),
      ],
      const SizedBox(height: 12),
      if (_downloading)
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            LinearProgressIndicator(value: _progress > 0 ? _progress / 100 : null),
            const SizedBox(height: 4),
            Text('$_progress%', textAlign: TextAlign.center),
          ],
        )
      else
        FilledButton.tonalIcon(
          onPressed: _downloadModel,
          icon: Icon(_downloaded ? Icons.memory : Icons.download),
          label: Text(_downloaded
              ? 'Загрузить в память'
              : 'Скачать (${preset.sizeLabel})'),
        ),
      const SizedBox(height: 8),
      Text(_downloadStatus, style: const TextStyle(fontSize: 13)),
    ];
  }

  List<Widget> _commonSection() => [
        const Text('Режим применения ответов'),
        RadioGroup<ApplyMode>(
          groupValue: _mode,
          onChanged: (v) => setState(() => _mode = v!),
          child: const Column(
            children: [
              RadioListTile<ApplyMode>(
                value: ApplyMode.suggest,
                title: Text('Подсказка (только показать)'),
              ),
              RadioListTile<ApplyMode>(
                value: ApplyMode.autofill,
                title: Text('Автозаполнение (вписать в форму)'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _lang,
          decoration: const InputDecoration(
            labelText: 'Целевой язык (необязательно)',
            border: OutlineInputBorder(),
            helperText:
                'Напр. «английский» — повышает точность языковых тестов.',
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _prompt,
          maxLines: 4,
          decoration: const InputDecoration(
            labelText: 'Свой системный промпт (необязательно)',
            border: OutlineInputBorder(),
            helperText: 'Пусто = встроенная роль филолога-переводчика.',
          ),
        ),
      ];

  @override
  void dispose() {
    _apiKey.dispose();
    _hfToken.dispose();
    _model.dispose();
    _lang.dispose();
    _prompt.dispose();
    super.dispose();
  }
}
