import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import '../ai/ai_client.dart';
import '../ai/gemini_client.dart';
import '../ai/local_engine.dart';
import '../ai/local_llm_client.dart';
import '../ai/local_models.dart';
import '../settings/app_settings.dart';
import '../settings/settings_repository.dart';
import 'form_controller.dart';

/// Main screen: a URL bar + an embedded WebView that loads a Google Form and
/// gets parsed/answered live.
class FormScreen extends StatefulWidget {
  const FormScreen({super.key, required this.settings});

  final SettingsRepository settings;

  @override
  State<FormScreen> createState() => _FormScreenState();
}

class _FormScreenState extends State<FormScreen> {
  final _urlController = TextEditingController();
  InAppWebViewController? _web;
  FormController? _form;
  String? _parserJs;
  String? _applyJs;

  @override
  void initState() {
    super.initState();
    _loadAssets();
  }

  Future<void> _loadAssets() async {
    _parserJs = await rootBundle.loadString('assets/js/parser.js');
    _applyJs = await rootBundle.loadString('assets/js/apply.js');
  }

  /// Build a fresh controller from current settings (provider/model/mode change).
  FormController _buildController() {
    final s = widget.settings.settings.value;
    final customPrompt =
        s.customSystemPrompt.isEmpty ? null : s.customSystemPrompt;
    final lang = s.targetLanguage.isEmpty ? null : s.targetLanguage;

    final AiClient client = switch (s.provider) {
      AiProvider.gemini => GeminiClient(
          apiKey: widget.settings.apiKey,
          model: s.model,
          customSystemPrompt: customPrompt,
          targetLanguage: lang,
        ),
      AiProvider.local => () {
          LocalEngine.instance.backend = s.localBackend;
          return LocalLlmClient(
            modelLabel: presetById(s.localModelId).displayName,
            customSystemPrompt: customPrompt,
            targetLanguage: lang,
          );
        }(),
    };

    return FormController(
      aiClient: client,
      applyMode: s.applyMode,
      runJs: (js) async => _web?.evaluateJavascript(source: js),
    );
  }

  void _loadForm() {
    final raw = _urlController.text.trim();
    if (raw.isEmpty || _web == null) return;
    final url = raw.startsWith('http') ? raw : 'https://$raw';
    _form = _buildController();
    setState(() {});
    _web!.loadUrl(urlRequest: URLRequest(url: WebUri(url)));
  }

  Future<void> _injectScripts() async {
    if (_web == null || _parserJs == null || _applyJs == null) return;
    // apply.js must be present before parser triggers answering.
    await _web!.evaluateJavascript(source: _applyJs!);
    await _web!.evaluateJavascript(source: _parserJs!);
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.settings.settings.value;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Google Forms AI'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.pushNamed(context, '/settings'),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _urlController,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      isDense: true,
                      border: OutlineInputBorder(),
                      hintText: 'Ссылка на Google-форму (…/viewform)',
                    ),
                    onSubmitted: (_) => _loadForm(),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(onPressed: _loadForm, child: const Text('Открыть')),
              ],
            ),
          ),
          _ModeBanner(mode: s.applyMode),
          Expanded(
            child: InAppWebView(
              initialSettings: InAppWebViewSettings(
                javaScriptEnabled: true,
                // A normal Chrome UA reduces the chance Google blocks sign-in
                // inside the embedded WebView ("disallowed_useragent").
                userAgent:
                    'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
              ),
              onWebViewCreated: (controller) {
                _web = controller;
                controller.addJavaScriptHandler(
                  handlerName: 'onQuestions',
                  callback: (args) {
                    final form = _form;
                    if (form == null || args.isEmpty) return;
                    // Normalize bridge maps (Map<Object?,Object?>) into plain
                    // JSON maps via a round-trip before parsing.
                    final list = jsonDecode(jsonEncode(args.first)) as List;
                    final raws = list
                        .map((raw) => Map<String, dynamic>.from(raw as Map))
                        .toList();
                    // Hand off to the controller's sequential queue; it drives
                    // pending → answer → apply one question at a time.
                    form.submit(raws);
                  },
                );
                controller.addJavaScriptHandler(
                  handlerName: 'log',
                  callback: (args) {
                    debugPrint('[gfa-js] ${args.join(' ')}');
                  },
                );
              },
              onLoadStop: (controller, url) => _injectScripts(),
            ),
          ),
          if (_form != null)
            ValueListenableBuilder<String>(
              valueListenable: _form!.status,
              builder: (_, text, __) => Container(
                width: double.infinity,
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                child: Text(text, style: const TextStyle(fontSize: 12)),
              ),
            ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }
}

class _ModeBanner extends StatelessWidget {
  const _ModeBanner({required this.mode});
  final ApplyMode mode;

  @override
  Widget build(BuildContext context) {
    final fill = mode == ApplyMode.autofill;
    return Container(
      width: double.infinity,
      color: const Color(0xFFFFF3CD),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Text(
        'Режим: ${fill ? 'автозаполнение' : 'подсказка'}. '
        'Форма НЕ отправляется автоматически — проверьте и отправьте сами.',
        style: const TextStyle(fontSize: 12, color: Color(0xFF664D03)),
      ),
    );
  }
}
