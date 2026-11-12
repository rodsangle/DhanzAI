import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

/// DHANZ AI brand colours: used by the logo, which keeps its navy and gold in every theme.
abstract final class DhanzColors {
  static const navy = Color(0xFF0B1A33);
  static const navyLight = Color(0xFF13284D);
  static const navySurface = Color(0xFF102244);
  static const gold = Color(0xFFD4AF37);
  static const goldLight = Color(0xFFE9CC6B);
  static const black = Color(0xFF07090E);
  static const white = Color(0xFFFFFFFF);
}

/// The themes the user can pick in Settings → Appearance.
enum DhanzTheme {
  midnightGold('Midnight Gold', 'Deep navy with warm gold', Brightness.dark),
  arcticLight('Arctic Light', 'Crisp and bright for daytime', Brightness.light),
  auroraTeal('Aurora Teal', 'Blue-green with mint and violet', Brightness.dark);

  const DhanzTheme(this.label, this.description, this.brightness);

  final String label;
  final String description;
  final Brightness brightness;

  DhanzPalette get palette => switch (this) {
    DhanzTheme.midnightGold => DhanzPalette.midnightGold,
    DhanzTheme.arcticLight => DhanzPalette.arcticLight,
    DhanzTheme.auroraTeal => DhanzPalette.auroraTeal,
  };

  ThemeData get data => _themes[this]!;
}

/// Every colour a theme is made of. Text colours are checked against the surfaces they sit on
/// (4.5:1 for text, 3:1 for borders and focus rings; see test/theme_test.dart).
@immutable
class DhanzPalette {
  const DhanzPalette({
    required this.brightness,
    required this.background,
    required this.surfaceLow,
    required this.surface,
    required this.surfaceHigh,
    required this.surfaceHighest,
    required this.accent,
    required this.onAccent,
    required this.accentContainer,
    required this.onAccentContainer,
    required this.secondary,
    required this.onSecondary,
    required this.secondaryContainer,
    required this.onSecondaryContainer,
    required this.tertiary,
    required this.onTertiary,
    required this.text,
    required this.muted,
    required this.outline,
    required this.outlineVariant,
    required this.error,
    required this.onError,
    required this.errorContainer,
    required this.onErrorContainer,
    required this.success,
    required this.warning,
    required this.codeBackground,
  });

  final Brightness brightness;

  /// Page background (`ColorScheme.surface`, the scaffold).
  final Color background;
  final Color surfaceLow;

  /// Cards, sidebar, dialogs (`surfaceContainer`).
  final Color surface;
  final Color surfaceHigh;

  /// Inputs, chips, the composer (`surfaceContainerHighest`).
  final Color surfaceHighest;
  final Color accent;
  final Color onAccent;
  final Color accentContainer;
  final Color onAccentContainer;

  /// Accent used for text: links, section labels (`ColorScheme.secondary`).
  final Color secondary;
  final Color onSecondary;
  final Color secondaryContainer;
  final Color onSecondaryContainer;
  final Color tertiary;
  final Color onTertiary;
  final Color text;

  /// Secondary text (`onSurfaceVariant`).
  final Color muted;

  /// Control borders and focus-adjacent strokes (3:1 against surfaces).
  final Color outline;

  /// Subtle dividers and card borders.
  final Color outlineVariant;
  final Color error;
  final Color onError;
  final Color errorContainer;
  final Color onErrorContainer;
  final Color success;
  final Color warning;
  final Color codeBackground;

  static const midnightGold = DhanzPalette(
    brightness: Brightness.dark,
    background: Color(0xFF0B1020),
    surfaceLow: Color(0xFF10172A),
    surface: Color(0xFF182033),
    surfaceHigh: Color(0xFF1E273C),
    surfaceHighest: Color(0xFF252F47),
    accent: Color(0xFFE6BD63),
    onAccent: Color(0xFF1A1408),
    accentContainer: Color(0xFF3A3020),
    onAccentContainer: Color(0xFFF7E2B3),
    secondary: Color(0xFFF0D08A),
    onSecondary: Color(0xFF1A1408),
    secondaryContainer: Color(0xFF2E3650),
    onSecondaryContainer: Color(0xFFF3F4F6),
    tertiary: Color(0xFF9FB4E8),
    onTertiary: Color(0xFF0B1020),
    text: Color(0xFFF3F4F6),
    muted: Color(0xFFA8B0C0),
    outline: Color(0xFF6E7891),
    outlineVariant: Color(0xFF2C3550),
    error: Color(0xFFFF8A80),
    onError: Color(0xFF3A0A06),
    errorContainer: Color(0xFF5C1A16),
    onErrorContainer: Color(0xFFFFDAD5),
    success: Color(0xFF6FD39A),
    warning: Color(0xFFF2B35B),
    codeBackground: Color(0xFF0F1526),
  );

  static const arcticLight = DhanzPalette(
    brightness: Brightness.light,
    background: Color(0xFFF7FAFF),
    surfaceLow: Color(0xFFFBFCFF),
    surface: Color(0xFFFFFFFF),
    surfaceHigh: Color(0xFFF1F6FF),
    surfaceHighest: Color(0xFFEAF2FF),
    // The mockup's #176BFF is a little light for small text on the pale backgrounds (4.4:1).
    accent: Color(0xFF135FEA),
    onAccent: Color(0xFFFFFFFF),
    accentContainer: Color(0xFFD6E5FF),
    onAccentContainer: Color(0xFF0A2E73),
    secondary: Color(0xFF0F55D6),
    onSecondary: Color(0xFFFFFFFF),
    secondaryContainer: Color(0xFFEAF2FF),
    onSecondaryContainer: Color(0xFF14213D),
    tertiary: Color(0xFF5B4BC4),
    onTertiary: Color(0xFFFFFFFF),
    text: Color(0xFF14213D),
    muted: Color(0xFF59677D),
    outline: Color(0xFF7A879D),
    outlineVariant: Color(0xFFD7E1F0),
    error: Color(0xFFC62828),
    onError: Color(0xFFFFFFFF),
    errorContainer: Color(0xFFFDE3E1),
    onErrorContainer: Color(0xFF6B0F0F),
    success: Color(0xFF17703D),
    warning: Color(0xFF8F5400),
    codeBackground: Color(0xFFF3F7FD),
  );

  static const auroraTeal = DhanzPalette(
    brightness: Brightness.dark,
    background: Color(0xFF062B33),
    surfaceLow: Color(0xFF0A333C),
    surface: Color(0xFF103F49),
    surfaceHigh: Color(0xFF144651),
    surfaceHighest: Color(0xFF194F5B),
    accent: Color(0xFF65E8CF),
    onAccent: Color(0xFF03231E),
    accentContainer: Color(0xFF14574F),
    onAccentContainer: Color(0xFFC9FBEF),
    // The mockup's violet (#9475E8) is too dark for text on teal (3.3:1); a lighter shade is used
    // for links and labels, the original tone for violet containers.
    secondary: Color(0xFFC4B1F8),
    onSecondary: Color(0xFF1E1240),
    secondaryContainer: Color(0xFF3B3470),
    onSecondaryContainer: Color(0xFFEDE6FF),
    tertiary: Color(0xFF9475E8),
    onTertiary: Color(0xFF130A33),
    text: Color(0xFFEDFFFA),
    muted: Color(0xFFA0C4C5),
    outline: Color(0xFF73AAB0),
    outlineVariant: Color(0xFF235A65),
    error: Color(0xFFFF9C8F),
    onError: Color(0xFF3D0B05),
    errorContainer: Color(0xFF5E211B),
    onErrorContainer: Color(0xFFFFDAD4),
    success: Color(0xFF7BE3A3),
    warning: Color(0xFFF3C46B),
    codeBackground: Color(0xFF052229),
  );

  ColorScheme get colorScheme => ColorScheme(
    brightness: brightness,
    primary: accent,
    onPrimary: onAccent,
    primaryContainer: accentContainer,
    onPrimaryContainer: onAccentContainer,
    secondary: secondary,
    onSecondary: onSecondary,
    secondaryContainer: secondaryContainer,
    onSecondaryContainer: onSecondaryContainer,
    tertiary: tertiary,
    onTertiary: onTertiary,
    tertiaryContainer: secondaryContainer,
    onTertiaryContainer: onSecondaryContainer,
    error: error,
    onError: onError,
    errorContainer: errorContainer,
    onErrorContainer: onErrorContainer,
    surface: background,
    onSurface: text,
    onSurfaceVariant: muted,
    surfaceDim: background,
    surfaceBright: surfaceHighest,
    surfaceContainerLowest: background,
    surfaceContainerLow: surfaceLow,
    surfaceContainer: surface,
    surfaceContainerHigh: surfaceHigh,
    surfaceContainerHighest: surfaceHighest,
    outline: outline,
    outlineVariant: outlineVariant,
    inverseSurface: text,
    onInverseSurface: background,
    inversePrimary: brightness == Brightness.dark ? onAccentContainer : accentContainer,
    shadow: const Color(0xFF000000),
    scrim: const Color(0xFF000000),
    surfaceTint: Colors.transparent,
  );
}

/// Colours Material's ColorScheme has no slot for. Read with `DhanzSemanticColors.of(context)`.
@immutable
class DhanzSemanticColors extends ThemeExtension<DhanzSemanticColors> {
  const DhanzSemanticColors({required this.success, required this.warning, required this.codeBackground});

  final Color success;
  final Color warning;
  final Color codeBackground;

  static DhanzSemanticColors of(BuildContext context) =>
      Theme.of(context).extension<DhanzSemanticColors>() ?? DhanzTheme.midnightGold.data.extension()!;

  @override
  DhanzSemanticColors copyWith({Color? success, Color? warning, Color? codeBackground}) => DhanzSemanticColors(
    success: success ?? this.success,
    warning: warning ?? this.warning,
    codeBackground: codeBackground ?? this.codeBackground,
  );

  @override
  DhanzSemanticColors lerp(DhanzSemanticColors? other, double t) => other == null
      ? this
      : DhanzSemanticColors(
          success: Color.lerp(success, other.success, t)!,
          warning: Color.lerp(warning, other.warning, t)!,
          codeBackground: Color.lerp(codeBackground, other.codeBackground, t)!,
        );
}

/// Shared shape and spacing tokens.
abstract final class DhanzRadii {
  static const control = 14.0;
  static const card = 18.0;
  static const dialog = 20.0;
  static const chip = 10.0;
}

ThemeData buildDhanzTheme(DhanzPalette p) {
  final scheme = p.colorScheme;
  final control = BorderRadius.circular(DhanzRadii.control);
  final rounded = RoundedRectangleBorder(borderRadius: control);
  final dark = p.brightness == Brightness.dark;
  final base = ThemeData(useMaterial3: true, colorScheme: scheme, brightness: p.brightness);
  final text = base.textTheme.apply(bodyColor: p.text, displayColor: p.text);
  return base.copyWith(
    scaffoldBackgroundColor: p.background,
    canvasColor: p.background,
    visualDensity: VisualDensity.adaptivePlatformDensity,
    textTheme: text,
    dividerColor: p.outlineVariant,
    // Keyboard focus stays visible on every surface.
    focusColor: p.accent.withValues(alpha: 0.18),
    hoverColor: p.text.withValues(alpha: 0.05),
    splashFactory: InkSparkle.splashFactory,
    extensions: [DhanzSemanticColors(success: p.success, warning: p.warning, codeBackground: p.codeBackground)],
    appBarTheme: AppBarTheme(
      backgroundColor: p.background,
      foregroundColor: p.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      surfaceTintColor: Colors.transparent,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: p.surfaceHighest,
      hintStyle: TextStyle(color: p.muted),
      labelStyle: TextStyle(color: p.muted),
      floatingLabelStyle: TextStyle(color: p.secondary),
      helperStyle: TextStyle(color: p.muted),
      prefixIconColor: p.muted,
      suffixIconColor: p.muted,
      border: OutlineInputBorder(borderRadius: control, borderSide: BorderSide.none),
      enabledBorder: OutlineInputBorder(
        borderRadius: control,
        borderSide: BorderSide(color: p.outlineVariant),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: control,
        borderSide: BorderSide(color: p.accent, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: control,
        borderSide: BorderSide(color: p.error),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: control,
        borderSide: BorderSide(color: p.error, width: 1.5),
      ),
      disabledBorder: OutlineInputBorder(borderRadius: control, borderSide: BorderSide.none),
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
      style: OutlinedButton.styleFrom(
        shape: rounded,
        minimumSize: const Size(64, 50),
        foregroundColor: p.text,
        side: BorderSide(color: p.outline),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: p.secondary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(DhanzRadii.chip)),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(style: IconButton.styleFrom(foregroundColor: p.muted)),
    cardTheme: CardThemeData(
      color: p.surface,
      elevation: 0,
      margin: const EdgeInsets.all(4),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(DhanzRadii.card),
        side: BorderSide(color: p.outlineVariant),
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: p.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 6,
      shadowColor: Colors.black.withValues(alpha: dark ? 0.5 : 0.18),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(DhanzRadii.dialog)),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: p.surface,
      surfaceTintColor: Colors.transparent,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(DhanzRadii.dialog))),
    ),
    drawerTheme: DrawerThemeData(backgroundColor: p.surfaceLow, surfaceTintColor: Colors.transparent),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: p.surfaceLow,
      indicatorColor: p.accentContainer,
      selectedIconTheme: IconThemeData(color: p.onAccentContainer),
      unselectedIconTheme: IconThemeData(color: p.muted),
    ),
    listTileTheme: ListTileThemeData(
      iconColor: p.muted,
      textColor: p.text,
      selectedColor: p.secondary,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(DhanzRadii.control)),
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: p.surfaceHigh,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(DhanzRadii.control),
        side: BorderSide(color: p.outlineVariant),
      ),
    ),
    menuTheme: MenuThemeData(
      style: MenuStyle(
        backgroundColor: WidgetStatePropertyAll(p.surfaceHigh),
        surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: p.surfaceHighest,
      selectedColor: p.accentContainer,
      labelStyle: TextStyle(color: p.text),
      secondaryLabelStyle: TextStyle(color: p.onAccentContainer),
      side: BorderSide(color: p.outlineVariant),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(DhanzRadii.chip)),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        selectedBackgroundColor: p.accentContainer,
        selectedForegroundColor: p.onAccentContainer,
        foregroundColor: p.text,
        side: BorderSide(color: p.outline),
      ),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.disabled)
            ? p.muted.withValues(alpha: 0.5)
            : s.contains(WidgetState.selected)
            ? p.onAccent
            : p.muted,
      ),
      trackColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? p.accent : p.surfaceHighest,
      ),
      trackOutlineColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? Colors.transparent : p.outline,
      ),
    ),
    checkboxTheme: CheckboxThemeData(
      side: BorderSide(color: p.outline, width: 1.5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
    ),
    tabBarTheme: TabBarThemeData(
      labelColor: p.secondary,
      unselectedLabelColor: p.muted,
      indicatorColor: p.accent,
      dividerColor: p.outlineVariant,
    ),
    dataTableTheme: DataTableThemeData(
      headingRowColor: WidgetStatePropertyAll(p.surfaceHigh),
      headingTextStyle: text.labelLarge?.copyWith(color: p.text, fontWeight: FontWeight.w600),
      dataTextStyle: text.bodyMedium?.copyWith(color: p.text),
      dividerThickness: 1,
      decoration: BoxDecoration(
        border: Border.all(color: p.outlineVariant),
        borderRadius: BorderRadius.circular(DhanzRadii.chip),
      ),
    ),
    dividerTheme: DividerThemeData(color: p.outlineVariant, thickness: 1, space: 1),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: p.accent,
      linearTrackColor: p.surfaceHighest,
      circularTrackColor: Colors.transparent,
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(color: p.text, borderRadius: BorderRadius.circular(8)),
      textStyle: TextStyle(color: p.background, fontSize: 12),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: p.text,
      contentTextStyle: TextStyle(color: p.background),
      actionTextColor: dark ? p.onAccent : p.accentContainer,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(DhanzRadii.control)),
    ),
    badgeTheme: BadgeThemeData(backgroundColor: p.error, textColor: p.onError),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: p.accent,
      selectionColor: p.accent.withValues(alpha: 0.3),
      selectionHandleColor: p.accent,
    ),
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

final Map<DhanzTheme, ThemeData> _themes = {for (final t in DhanzTheme.values) t: buildDhanzTheme(t.palette)};

/// What the user picked: one theme, or follow the system (Arctic Light by day, Midnight Gold at night).
enum ThemePreference {
  system,
  midnightGold,
  arcticLight,
  auroraTeal;

  /// The theme shown for this preference when the system is in [platform] brightness.
  DhanzTheme resolve(Brightness platform) => switch (this) {
    ThemePreference.system => platform == Brightness.dark ? DhanzTheme.midnightGold : DhanzTheme.arcticLight,
    ThemePreference.midnightGold => DhanzTheme.midnightGold,
    ThemePreference.arcticLight => DhanzTheme.arcticLight,
    ThemePreference.auroraTeal => DhanzTheme.auroraTeal,
  };

  /// `MaterialApp` wiring: the light and dark themes plus which of them to use.
  ThemeData get lightTheme => resolve(Brightness.light).data;
  ThemeData get darkTheme => resolve(Brightness.dark).data;
  ThemeMode get themeMode => this == ThemePreference.system
      ? ThemeMode.system
      : resolve(Brightness.light).brightness == Brightness.dark
      ? ThemeMode.dark
      : ThemeMode.light;

  /// The pre-0.9 setting (`ThemeMode` name) closest to this one, kept for older app builds.
  String get legacyName => themeMode.name;

  /// Reads the stored preference, falling back to the old light/dark/system setting.
  /// [stored] may also be a 0.9 test-build `theme_style` value; its "original" choice falls back too.
  /// Nothing stored at all means Midnight Gold, the previous default dark theme.
  static ThemePreference fromStored({String? stored, String? legacy}) {
    final current = ThemePreference.values.asNameMap()[stored];
    if (current != null) return current;
    return switch (legacy) {
      'light' => ThemePreference.arcticLight,
      'system' => ThemePreference.system,
      _ => ThemePreference.midnightGold,
    };
  }
}

/// The previous fixed themes, kept for code that only needs "the" light or dark theme.
ThemeData get dhanzDarkTheme => DhanzTheme.midnightGold.data;
ThemeData get dhanzLightTheme => DhanzTheme.arcticLight.data;
