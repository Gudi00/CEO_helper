import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_settings.dart';

/// Loads/saves settings. The Gemini API key is kept in the platform secure
/// store (Keychain / Keystore); the rest in SharedPreferences.
///
/// Exposes the current [AppSettings] as a [ValueListenable] so the UI and the
/// WebView controller react to changes without a heavier state framework.
class SettingsRepository {
  SettingsRepository({FlutterSecureStorage? secure}) : _secure = secure ?? const FlutterSecureStorage();

  static const _kApiKey = 'gemini_api_key';
  static const _kHfToken = 'hf_token';
  static const _kProvider = 'provider';
  static const _kModel = 'model';
  static const _kLocalModel = 'local_model_id';
  static const _kLocalBackend = 'local_backend';
  static const _kApplyMode = 'apply_mode';
  static const _kTargetLang = 'target_language';
  static const _kCustomPrompt = 'custom_system_prompt';

  final FlutterSecureStorage _secure;
  final ValueNotifier<AppSettings> settings = ValueNotifier(const AppSettings());

  String _apiKey = '';
  String get apiKey => _apiKey;

  String _hfToken = '';
  String get hfToken => _hfToken;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    settings.value = AppSettings(
      provider: AiProvider.fromWire(prefs.getString(_kProvider)),
      model: prefs.getString(_kModel) ?? AppSettings.defaultModel,
      localModelId:
          prefs.getString(_kLocalModel) ?? AppSettings.defaultLocalModelId,
      localBackend: LocalBackend.fromWire(prefs.getString(_kLocalBackend)),
      applyMode: ApplyMode.fromWire(prefs.getString(_kApplyMode)),
      targetLanguage: prefs.getString(_kTargetLang) ?? '',
      customSystemPrompt: prefs.getString(_kCustomPrompt) ?? '',
    );
    _apiKey = await _secure.read(key: _kApiKey) ?? '';
    _hfToken = await _secure.read(key: _kHfToken) ?? '';
  }

  Future<void> save(AppSettings next) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kProvider, next.provider.wire);
    await prefs.setString(_kModel, next.model);
    await prefs.setString(_kLocalModel, next.localModelId);
    await prefs.setString(_kLocalBackend, next.localBackend.wire);
    await prefs.setString(_kApplyMode, next.applyMode.wire);
    await prefs.setString(_kTargetLang, next.targetLanguage);
    await prefs.setString(_kCustomPrompt, next.customSystemPrompt);
    settings.value = next;
  }

  Future<void> saveApiKey(String key) async {
    _apiKey = key.trim();
    if (_apiKey.isEmpty) {
      await _secure.delete(key: _kApiKey);
    } else {
      await _secure.write(key: _kApiKey, value: _apiKey);
    }
  }

  Future<void> saveHfToken(String token) async {
    _hfToken = token.trim();
    if (_hfToken.isEmpty) {
      await _secure.delete(key: _kHfToken);
    } else {
      await _secure.write(key: _kHfToken, value: _hfToken);
    }
  }
}
