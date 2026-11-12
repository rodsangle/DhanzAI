import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/platform/app_version.dart';
import 'package:dhanz_ai/core/platform/updates.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/core/theme.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/router.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

double contrast(Color a, Color b) {
  final la = a.computeLuminance(), lb = b.computeLuminance();
  final (hi, lo) = la > lb ? (la, lb) : (lb, la);
  return (hi + 0.05) / (lo + 0.05);
}

void main() {
  late FakeBackend backend;
  late MemorySecureStore store;

  List<Override> overrides() => [
    secureStoreProvider.overrideWithValue(store),
    apiClientProvider.overrideWith(
      (ref) => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client),
    ),
    appVersionProvider.overrideWith((ref) async => '0.9.0'),
    updatePlatformProvider.overrideWithValue(null),
  ];

  setUp(() {
    backend = FakeBackend();
    store = MemorySecureStore();
  });

  Future<ThemePreference> loaded(ProviderContainer c) async {
    c.read(themePreferenceProvider);
    await Future<void>.delayed(Duration.zero); // let the stored value load
    return c.read(themePreferenceProvider);
  }

  group('preference migration', () {
    test('old light/dark/system choices map to the new themes', () {
      expect(ThemePreference.fromStored(legacy: 'light'), ThemePreference.arcticLight);
      expect(ThemePreference.fromStored(legacy: 'dark'), ThemePreference.midnightGold);
      expect(ThemePreference.fromStored(legacy: 'system'), ThemePreference.system);
      expect(ThemePreference.fromStored(), ThemePreference.midnightGold, reason: 'the previous default was dark');
      expect(ThemePreference.fromStored(stored: 'bogus', legacy: 'bogus'), ThemePreference.midnightGold);
      expect(
        ThemePreference.fromStored(stored: 'auroraTeal', legacy: 'light'),
        ThemePreference.auroraTeal,
        reason: 'a saved new-style choice wins over the old key',
      );
    });

    test('a stored light preference becomes Arctic Light once, leaving other settings alone', () async {
      store.values.addAll({
        StoreKeys.themeMode: 'light',
        StoreKeys.apiUrl: 'https://dhanz.example',
        StoreKeys.refreshToken: 'refresh-123',
      });
      final c = ProviderContainer(overrides: overrides());
      addTearDown(c.dispose);
      expect(await loaded(c), ThemePreference.arcticLight);
      expect(store.values[StoreKeys.appTheme], 'arcticLight');
      expect(store.values[StoreKeys.themeMode], 'light');
      expect(store.values[StoreKeys.apiUrl], 'https://dhanz.example');
      expect(store.values[StoreKeys.refreshToken], 'refresh-123');
    });

    test('a theme picked in a 0.9 test build carries over; its "original" falls back', () async {
      store.values[StoreKeys.themeStyle] = 'auroraTeal';
      final c = ProviderContainer(overrides: overrides());
      addTearDown(c.dispose);
      expect(await loaded(c), ThemePreference.auroraTeal);
      expect(store.values[StoreKeys.appTheme], 'auroraTeal');
      expect(ThemePreference.fromStored(stored: 'original', legacy: 'light'), ThemePreference.arcticLight);
    });

    test('a choice survives a restart and keeps the old key in step for older builds', () async {
      final first = ProviderContainer(overrides: overrides());
      await loaded(first);
      await first.read(themePreferenceProvider.notifier).set(ThemePreference.auroraTeal);
      first.dispose();
      expect(store.values[StoreKeys.appTheme], 'auroraTeal');
      expect(store.values[StoreKeys.themeMode], 'dark');

      final second = ProviderContainer(overrides: overrides());
      addTearDown(second.dispose);
      expect(await loaded(second), ThemePreference.auroraTeal);

      await second.read(themePreferenceProvider.notifier).set(ThemePreference.system);
      expect(store.values[StoreKeys.themeMode], 'system');
    });
  });

  group('system mode', () {
    test('follow system is Arctic Light by day and Midnight Gold at night', () {
      const p = ThemePreference.system;
      expect(p.resolve(Brightness.light), DhanzTheme.arcticLight);
      expect(p.resolve(Brightness.dark), DhanzTheme.midnightGold);
      expect(p.themeMode, ThemeMode.system);
      expect(ThemePreference.auroraTeal.themeMode, ThemeMode.dark);
      expect(ThemePreference.arcticLight.themeMode, ThemeMode.light);
      expect(ThemePreference.auroraTeal.resolve(Brightness.light), DhanzTheme.auroraTeal);
    });

    testWidgets('the app follows the device brightness only in Follow system', (tester) async {
      store.values[StoreKeys.appTheme] = 'system';
      tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
      addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
      await tester.pumpWidget(ProviderScope(overrides: overrides(), child: const DhanzApp()));
      await tester.pumpAndSettle();
      Color background() => Theme.of(tester.element(find.byType(Scaffold).first)).scaffoldBackgroundColor;
      expect(background(), DhanzPalette.arcticLight.background);

      tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
      await tester.pumpAndSettle();
      expect(background(), DhanzPalette.midnightGold.background);

      final container = ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));
      await container.read(themePreferenceProvider.notifier).set(ThemePreference.arcticLight);
      await tester.pumpAndSettle();
      expect(background(), DhanzPalette.arcticLight.background, reason: 'an explicit theme ignores the device');
    });
  });

  testWidgets('Settings shows a preview of every theme and switching applies at once', (tester) async {
    tester.view.physicalSize = const Size(1280, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await ApiClient(
      store: store,
      baseUrl: 'http://test',
      clientFactory: backend.client,
    ).register('ada@example.com', 'correct-horse-9', 'Ada');
    store.values[StoreKeys.themeMode] = 'dark'; // a user of the previous version
    await tester.pumpWidget(ProviderScope(overrides: overrides(), child: const DhanzApp()));
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));
    container.read(routerProvider).go('/settings');
    await tester.pumpAndSettle();

    for (final label in ['Follow system', 'Midnight Gold', 'Arctic Light', 'Aurora Teal']) {
      expect(find.text(label), findsOneWidget);
    }
    expect(tester.getSemantics(find.bySemanticsLabel('Midnight Gold theme')), isSemantics(isSelected: true));
    expect(tester.getSemantics(find.bySemanticsLabel('Aurora Teal theme')), isSemantics(isSelected: false));

    await tester.tap(find.text('Aurora Teal'));
    await tester.pumpAndSettle();
    final theme = Theme.of(tester.element(find.text('Settings')));
    expect(theme.scaffoldBackgroundColor, DhanzPalette.auroraTeal.background);
    expect(theme.colorScheme.primary, DhanzPalette.auroraTeal.accent);
    expect(store.values[StoreKeys.appTheme], 'auroraTeal');
    expect(tester.getSemantics(find.bySemanticsLabel('Aurora Teal theme')), isSemantics(isSelected: true));
    // Other settings screens still render (profile, account) with the new theme.
    expect(find.text('Ada'), findsOneWidget);
  });

  group('palettes', () {
    for (final t in DhanzTheme.values) {
      test('${t.label}: readable text and visible controls', () {
        final p = t.palette;
        final surfaces = {'background': p.background, 'surface': p.surface, 'input': p.surfaceHighest};
        final texts = {
          'text': p.text,
          'muted': p.muted,
          'accent': p.accent,
          'secondary': p.secondary,
          'error': p.error,
          'success': p.success,
          'warning': p.warning,
        };
        for (final s in surfaces.entries) {
          for (final x in texts.entries) {
            expect(contrast(x.value, s.value), greaterThanOrEqualTo(4.5), reason: '${x.key} on ${s.key}');
          }
          expect(contrast(p.outline, s.value), greaterThanOrEqualTo(3), reason: 'outline on ${s.key}');
        }
        expect(contrast(p.onAccent, p.accent), greaterThanOrEqualTo(4.5), reason: 'button text');
        expect(contrast(p.onError, p.error), greaterThanOrEqualTo(4.5), reason: 'error button text');
        expect(contrast(p.onAccentContainer, p.accentContainer), greaterThanOrEqualTo(4.5), reason: 'selected');
        expect(contrast(p.onSecondaryContainer, p.secondaryContainer), greaterThanOrEqualTo(4.5));
        expect(contrast(p.onErrorContainer, p.errorContainer), greaterThanOrEqualTo(4.5));
        expect(contrast(p.text, p.codeBackground), greaterThanOrEqualTo(4.5), reason: 'code');
      });

      test('${t.label}: ThemeData uses the palette everywhere', () {
        final data = t.data;
        final p = t.palette;
        expect(data.brightness, t.brightness);
        expect(data.scaffoldBackgroundColor, p.background);
        expect(data.colorScheme.surfaceContainer, p.surface);
        expect(data.colorScheme.onSurfaceVariant, p.muted);
        expect(data.cardTheme.color, p.surface);
        expect(data.dialogTheme.backgroundColor, p.surface);
        expect(data.extension<DhanzSemanticColors>()!.codeBackground, p.codeBackground);
        expect(data.inputDecorationTheme.focusedBorder!.borderSide.color, p.accent);
      });
    }

    test('mockup colours are kept where they are readable', () {
      expect(DhanzPalette.midnightGold.background, const Color(0xFF0B1020));
      expect(DhanzPalette.midnightGold.accent, const Color(0xFFE6BD63));
      expect(DhanzPalette.arcticLight.background, const Color(0xFFF7FAFF));
      expect(DhanzPalette.arcticLight.text, const Color(0xFF14213D));
      expect(DhanzPalette.auroraTeal.background, const Color(0xFF062B33));
      expect(DhanzPalette.auroraTeal.accent, const Color(0xFF65E8CF));
      expect(DhanzPalette.auroraTeal.tertiary, const Color(0xFF9475E8));
    });
  });
}
