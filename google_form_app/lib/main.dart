import 'package:flutter/material.dart';

import 'app.dart';
import 'settings/settings_repository.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final settings = SettingsRepository();
  await settings.load();
  runApp(GoogleFormApp(settings: settings));
}
