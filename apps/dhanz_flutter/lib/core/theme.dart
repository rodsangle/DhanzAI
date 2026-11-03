import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

/// Stored names are stable preference IDs. Original retains the previous mode choice.
enum DhanzThemeStyle { original, midnightGold, arcticLight, auroraTeal, system }

extension DhanzThemeStyleInfo on DhanzThemeStyle {
  String get label => switch (this) {
    DhanzThemeStyle.original => 'Original Dhanz',
    DhanzThemeStyle.midnightGold => 'Midnight Gold',
    DhanzThemeStyle.arcticLight => 'Arctic Light',
    DhanzThemeStyle.auroraTeal => 'Aurora Teal',
    DhanzThemeStyle.system => 'Follow system',
  };

  String get description => switch (this) {
    DhanzThemeStyle.original => 'Classic navy and gold, with your existing light/dark setting.',
    DhanzThemeStyle.midnightGold => 'Deep midnight surfaces with warm gold accents.',
    DhanzThemeStyle.arcticLight => 'Bright, airy surfaces with crisp blue accents.',
    DhanzThemeStyle.auroraTeal => 'Rich teal surfaces with a soft mint accent.',
    DhanzThemeStyle.system => 'Arctic Light in light mode; Midnight Gold in dark mode.',
  };

  ThemeMode mode(ThemeMode originalMode) => switch (this) {
    DhanzThemeStyle.original => originalMode,
    DhanzThemeStyle.arcticLight => ThemeMode.light,
    DhanzThemeStyle.midnightGold || DhanzThemeStyle.auroraTeal => ThemeMode.dark,
    DhanzThemeStyle.system => ThemeMode.system,
  };

  ThemeData theme(Brightness brightness) => switch (this) {
    DhanzThemeStyle.original => brightness == Brightness.light ? dhanzLightTheme : dhanzDarkTheme,
    DhanzThemeStyle.midnightGold => midnightGoldTheme,
    DhanzThemeStyle.arcticLight => arcticLightTheme,
    DhanzThemeStyle.auroraTeal => auroraTealTheme,
    DhanzThemeStyle.system => brightness == Brightness.light ? arcticLightTheme : midnightGoldTheme,
  };
}

/// DHANZ AI brand palette: dark navy, gold accents, white text, black secondary surfaces.
abstract final class DhanzColors {
  static const navy = Color(0xFF0B1A33);
  static const navyLight = Color(0xFF13284D);
  static const navySurface = Color(0xFF102244);
  static const gold = Color(0xFFD4AF37);
  static const goldLight = Color(0xFFE9CC6B);
  static const black = Color(0xFF07090E);
  static const white = Color(0xFFFFFFFF);
  static const mist = Color(0xFFF4F6FA);
  static const error = Color(0xFFE5484D);
}

ThemeData _base(ColorScheme scheme) {
  final rounded = RoundedRectangleBorder(borderRadius: BorderRadius.circular(14));
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: scheme.surface,
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: scheme.primary,
      selectionColor: scheme.primary.withValues(alpha: 0.25),
      selectionHandleColor: scheme.primary,
    ),
    dividerTheme: DividerThemeData(color: scheme.outlineVariant, thickness: 1),
    visualDensity: VisualDensity.adaptivePlatformDensity,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      foregroundColor: scheme.onSurface,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerHighest,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: scheme.secondary, width: 1.5),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: rounded,
        minimumSize: const Size(64, 50),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(shape: rounded, minimumSize: const Size(64, 50)),
    ),
    cardTheme: CardThemeData(
      color: scheme.surfaceContainer,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    ),
    dialogTheme: DialogThemeData(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20))),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {
        TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
        TargetPlatform.windows: FadeForwardsPageTransitionsBuilder(),
        TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
        TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
      },
    ),
  );
}

final ThemeData dhanzDarkTheme = _base(
  const ColorScheme(
    brightness: Brightness.dark,
    primary: DhanzColors.gold,
    onPrimary: DhanzColors.navy,
    secondary: DhanzColors.goldLight,
    onSecondary: DhanzColors.navy,
    error: DhanzColors.error,
    onError: DhanzColors.white,
    surface: DhanzColors.navy,
    onSurface: DhanzColors.white,
    surfaceContainerLowest: DhanzColors.black,
    surfaceContainerLow: Color(0xFF0D1E3B),
    surfaceContainer: DhanzColors.navySurface,
    surfaceContainerHigh: DhanzColors.navyLight,
    surfaceContainerHighest: Color(0xFF1A3260),
    onSurfaceVariant: Color(0xFFB8C2D6),
    outline: Color(0xFF3A4E75),
    outlineVariant: Color(0xFF243A63),
  ),
);

final ThemeData dhanzLightTheme = _base(
  const ColorScheme(
    brightness: Brightness.light,
    primary: DhanzColors.navy,
    onPrimary: DhanzColors.white,
    secondary: Color(0xFFB8921E),
    onSecondary: DhanzColors.white,
    error: DhanzColors.error,
    onError: DhanzColors.white,
    surface: DhanzColors.white,
    onSurface: DhanzColors.navy,
    surfaceContainerLowest: DhanzColors.white,
    surfaceContainerLow: Color(0xFFF8F9FC),
    surfaceContainer: DhanzColors.mist,
    surfaceContainerHigh: Color(0xFFEBEEF5),
    surfaceContainerHighest: Color(0xFFE3E8F1),
    onSurfaceVariant: Color(0xFF4A5875),
    outline: Color(0xFFB9C3D6),
    outlineVariant: Color(0xFFD9DFEA),
  ),
);

ThemeData _conceptTheme({
  required Brightness brightness,
  required Color background,
  required Color surface,
  required Color accent,
  required Color text,
  required Color muted,
  required Color elevated,
  required Color border,
}) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(seedColor: accent, brightness: brightness).copyWith(
    primary: accent,
    onPrimary: dark ? background : Colors.white,
    secondary: accent,
    onSecondary: dark ? background : Colors.white,
    primaryContainer: dark ? elevated : const Color(0xFFDCE8FF),
    onPrimaryContainer: text,
    secondaryContainer: dark ? elevated : const Color(0xFFDCE8FF),
    onSecondaryContainer: text,
    surface: background,
    onSurface: text,
    onSurfaceVariant: muted,
    surfaceContainerLowest: background,
    surfaceContainerLow: surface,
    surfaceContainer: surface,
    surfaceContainerHigh: elevated,
    surfaceContainerHighest: elevated,
    outline: border,
    outlineVariant: border.withValues(alpha: 0.55),
    surfaceTint: accent,
  );
  return _base(scheme);
}

final midnightGoldTheme = _conceptTheme(
  brightness: Brightness.dark,
  background: const Color(0xFF0B1020),
  surface: const Color(0xFF182033),
  accent: const Color(0xFFE6BD63),
  text: const Color(0xFFF3F4F6),
  muted: const Color(0xFFB7C1D5),
  elevated: const Color(0xFF253149),
  border: const Color(0xFF697991),
);

final arcticLightTheme = _conceptTheme(
  brightness: Brightness.light,
  background: const Color(0xFFF7FAFF),
  surface: Colors.white,
  accent: const Color(0xFF176BFF),
  text: const Color(0xFF14213D),
  muted: const Color(0xFF4B5C77),
  elevated: const Color(0xFFE8EFFA),
  border: const Color(0xFF71819B),
);

final auroraTealTheme = _conceptTheme(
  brightness: Brightness.dark,
  background: const Color(0xFF062B33),
  surface: const Color(0xFF103F49),
  accent: const Color(0xFF65E8CF),
  text: const Color(0xFFEDFFFA),
  muted: const Color(0xFFB2D6D5),
  elevated: const Color(0xFF19515A),
  border: const Color(0xFF699EAA),
);
