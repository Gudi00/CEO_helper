import 'package:flutter/material.dart';

import 'settings/settings_repository.dart';
import 'settings/settings_screen.dart';
import 'webview/form_screen.dart';

class GoogleFormApp extends StatelessWidget {
  const GoogleFormApp({super.key, required this.settings});

  final SettingsRepository settings;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder(
      valueListenable: settings.settings,
      builder: (context, _, __) {
        return MaterialApp(
          title: 'Google Forms AI',
          theme: ThemeData(
            colorSchemeSeed: const Color(0xFF2ecc71),
            useMaterial3: true,
          ),
          routes: {
            '/': (_) => FormScreen(settings: settings),
            '/settings': (_) => SettingsScreen(repo: settings),
          },
          initialRoute: '/',
        );
      },
    );
  }
}
