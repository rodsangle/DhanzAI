import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

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
