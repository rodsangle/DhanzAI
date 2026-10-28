import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/config.dart';
import 'core/providers.dart';
import 'core/theme.dart';
import 'router.dart';

void main() {
  runApp(const ProviderScope(child: DhanzApp()));
}

class DhanzApp extends ConsumerWidget {
  const DhanzApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: dhanzLightTheme,
      darkTheme: dhanzDarkTheme,
      themeMode: ref.watch(themeModeProvider),
      routerConfig: ref.watch(routerProvider),
    );
  }
}
