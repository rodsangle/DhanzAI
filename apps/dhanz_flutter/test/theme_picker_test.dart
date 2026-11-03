import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/core/theme.dart';
import 'package:dhanz_ai/features/settings/theme_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

ProviderContainer containerFor(SecureStore store) {
  final container = ProviderContainer(overrides: [secureStoreProvider.overrideWithValue(store)]);
  addTearDown(container.dispose);
  return container;
}

class DelayedStore extends MemorySecureStore {
  final readResult = Completer<String?>();
  @override
  Future<String?> read(String key) => key == StoreKeys.themeStyle ? readResult.future : super.read(key);
}

class SlowWriteStore extends MemorySecureStore {
  final finishFirstWrite = Completer<void>();
  @override
  Future<void> write(String key, String? value) async {
    if (value == DhanzThemeStyle.midnightGold.name) await finishFirstWrite.future;
    await super.write(key, value);
  }
}

Widget appearanceApp(SecureStore store, {GlobalKey? screenshotKey, double textScale = 1}) => ProviderScope(
  overrides: [secureStoreProvider.overrideWithValue(store)],
  child: Consumer(
    builder: (context, ref, _) {
      final style = ref.watch(themeStyleProvider);
      return MaterialApp(
        theme: style.theme(Brightness.light),
        darkTheme: style.theme(Brightness.dark),
        themeMode: style.mode(ref.watch(themeModeProvider)),
        home: Builder(
          builder: (context) => MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
            child: RepaintBoundary(
              key: screenshotKey,
              child: Scaffold(
                appBar: AppBar(title: const Text('Appearance')),
                body: const SingleChildScrollView(padding: EdgeInsets.symmetric(vertical: 16), child: ThemePicker()),
              ),
            ),
          ),
        ),
      );
    },
  ),
);

void main() {
  for (final mode in ThemeMode.values) {
    test('existing ${mode.name} preference retains original appearance', () async {
      final store = MemorySecureStore()..values[StoreKeys.themeMode] = mode.name;
      final container = containerFor(store);
      container.read(themeModeProvider);
      container.read(themeStyleProvider);
      await Future<void>.delayed(Duration.zero);
      final style = container.read(themeStyleProvider);
      expect(style, DhanzThemeStyle.original);
      expect(style.mode(container.read(themeModeProvider)), mode);
      expect(store.values.containsKey(StoreKeys.themeStyle), isFalse);
    });
  }

  test('each theme survives a fresh provider without modifying other preferences', () async {
    final store = MemorySecureStore()
      ..values[StoreKeys.themeMode] = 'light'
      ..values[StoreKeys.apiUrl] = 'https://dhanzai.com';
    for (final style in DhanzThemeStyle.values) {
      final first = containerFor(store);
      await first.read(themeStyleProvider.notifier).set(style);
      final restarted = containerFor(store);
      restarted.read(themeStyleProvider);
      await Future<void>.delayed(Duration.zero);
      expect(restarted.read(themeStyleProvider), style);
    }
    expect(store.values[StoreKeys.themeMode], 'light');
    expect(store.values[StoreKeys.apiUrl], 'https://dhanzai.com');
  });

  test('a delayed stored value cannot overwrite a new choice', () async {
    final store = DelayedStore();
    final container = containerFor(store);
    await container.read(themeStyleProvider.notifier).set(DhanzThemeStyle.auroraTeal);
    store.readResult.complete('midnightGold');
    await Future<void>.delayed(Duration.zero);
    expect(container.read(themeStyleProvider), DhanzThemeStyle.auroraTeal);
    expect(store.values[StoreKeys.themeStyle], 'auroraTeal');
  });

  test('rapid selections preserve the final choice even with a slow first save', () async {
    final store = SlowWriteStore();
    final controller = containerFor(store).read(themeStyleProvider.notifier);
    final first = controller.set(DhanzThemeStyle.midnightGold);
    final last = controller.set(DhanzThemeStyle.auroraTeal);
    store.finishFirstWrite.complete();
    await Future.wait([first, last]);
    expect(store.values[StoreKeys.themeStyle], 'auroraTeal');
  });

  test('unknown stored theme falls back without deleting legacy preferences', () async {
    final store = MemorySecureStore()
      ..values[StoreKeys.themeStyle] = 'future-theme'
      ..values[StoreKeys.themeMode] = 'light';
    final container = containerFor(store);
    container.read(themeStyleProvider);
    await Future<void>.delayed(Duration.zero);
    expect(container.read(themeStyleProvider), DhanzThemeStyle.original);
    expect(store.values[StoreKeys.themeMode], 'light');
  });

  testWidgets('selectable skins change actual app colors and save the selection', (tester) async {
    final store = MemorySecureStore();
    await tester.pumpWidget(appearanceApp(store));
    await tester.pumpAndSettle();
    for (final style in [DhanzThemeStyle.midnightGold, DhanzThemeStyle.arcticLight, DhanzThemeStyle.auroraTeal]) {
      final target = find.byKey(ValueKey('theme-${style.name}'));
      await tester.ensureVisible(target);
      await tester.tap(target);
      await tester.pumpAndSettle();
      final theme = Theme.of(tester.element(find.byType(ThemePicker)));
      expect(theme.colorScheme.primary, style.theme(Brightness.light).colorScheme.primary);
      expect(theme.scaffoldBackgroundColor, style.theme(Brightness.light).scaffoldBackgroundColor);
      expect(store.values[StoreKeys.themeStyle], style.name);
    }
  });

  testWidgets('Follow system updates when the device brightness changes', (tester) async {
    final store = MemorySecureStore()..values[StoreKeys.themeStyle] = 'system';
    addTearDown(tester.binding.platformDispatcher.clearPlatformBrightnessTestValue);
    tester.binding.platformDispatcher.platformBrightnessTestValue = Brightness.light;
    await tester.pumpWidget(appearanceApp(store));
    await tester.pumpAndSettle();
    expect(
      Theme.of(tester.element(find.byType(ThemePicker))).colorScheme.primary,
      arcticLightTheme.colorScheme.primary,
    );
    tester.binding.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
    await tester.pumpAndSettle();
    expect(
      Theme.of(tester.element(find.byType(ThemePicker))).colorScheme.primary,
      midnightGoldTheme.colorScheme.primary,
    );
  });

  testWidgets('theme cards can be selected with the keyboard', (tester) async {
    final store = MemorySecureStore();
    await tester.pumpWidget(appearanceApp(store));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(store.values[StoreKeys.themeStyle], 'midnightGold');
  });

  testWidgets('appearance picker fits a narrow screen with large text', (tester) async {
    tester.view.physicalSize = const Size(320, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(appearanceApp(MemorySecureStore(), textScale: 2));
    await tester.pumpAndSettle();
    for (final style in DhanzThemeStyle.values) {
      await tester.ensureVisible(find.byKey(ValueKey('theme-${style.name}')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    }
  });

  test('new theme text and filled-button colors have readable contrast', () {
    double ratio(Color a, Color b) {
      final x = a.computeLuminance(), y = b.computeLuminance();
      return x > y ? (x + 0.05) / (y + 0.05) : (y + 0.05) / (x + 0.05);
    }

    for (final theme in [midnightGoldTheme, arcticLightTheme, auroraTealTheme]) {
      final c = theme.colorScheme;
      expect(ratio(c.onSurface, c.surface), greaterThanOrEqualTo(4.5));
      expect(ratio(c.onSurfaceVariant, c.surfaceContainerHigh), greaterThanOrEqualTo(4.5));
      expect(ratio(c.primary, c.onPrimary), greaterThanOrEqualTo(4.5));
    }
  });

  if (const bool.fromEnvironment('DHANZ_THEME_SCREENSHOTS')) {
    setUpAll(() async {
      // Widget tests substitute Ahem by default. Load SDK fonts so published
      // previews show readable text and icons rather than test-font rectangles.
      final executable = Platform.resolvedExecutable.replaceAll('\\', '/');
      final marker = executable.indexOf('/bin/cache/');
      final sdk = Platform.environment['FLUTTER_ROOT'] ?? (marker < 0 ? null : executable.substring(0, marker));
      if (sdk == null) throw StateError('Set FLUTTER_ROOT to render theme previews with SDK fonts.');
      final fonts = '$sdk/bin/cache/artifacts/material_fonts';
      final text = FontLoader('Roboto');
      for (final name in ['Roboto-Regular.ttf', 'Roboto-Medium.ttf', 'Roboto-Bold.ttf']) {
        text.addFont(File('$fonts/$name').readAsBytes().then(ByteData.sublistView));
      }
      await text.load();
      final icons = FontLoader('MaterialIcons')
        ..addFont(File('$fonts/MaterialIcons-Regular.otf').readAsBytes().then(ByteData.sublistView));
      await icons.load();
    });
    for (final style in [DhanzThemeStyle.midnightGold, DhanzThemeStyle.arcticLight, DhanzThemeStyle.auroraTeal]) {
      testWidgets('capture ${style.label} appearance preview', (tester) async {
        tester.view.physicalSize = const Size(800, 1100);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final key = GlobalKey();
        final store = MemorySecureStore()..values[StoreKeys.themeStyle] = style.name;
        await tester.pumpWidget(appearanceApp(store, screenshotKey: key));
        await tester.pumpAndSettle();
        await tester.runAsync(() async {
          final boundary = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
          final image = await boundary.toImage();
          final data = await image.toByteData(format: ui.ImageByteFormat.png);
          await Directory('build/theme-previews').create(recursive: true);
          await File('build/theme-previews/${style.name}.png').writeAsBytes(data!.buffer.asUint8List());
          image.dispose();
        });
        expect(tester.takeException(), isNull);
      });
    }
  }
}
