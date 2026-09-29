import 'package:flutter/material.dart';

import 'app_colors.dart';
import 'color_scheme.dart';
import 'tokens.dart';

/// Builds the four [ThemeData]s used by `MaterialApp` (Design_System.md §2.1).
abstract final class AppTheme {
  static ThemeData get light => _build(AppColorSchemes.light);
  static ThemeData get dark => _build(AppColorSchemes.dark);
  static ThemeData get lightHighContrast =>
      _build(AppColorSchemes.lightHighContrast);
  static ThemeData get darkHighContrast =>
      _build(AppColorSchemes.darkHighContrast);

  static ThemeData _build(ColorScheme scheme) {
    final isDark = scheme.brightness == Brightness.dark;
    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      scaffoldBackgroundColor: scheme.surface,
      extensions: [
        isDark ? MoistureColors.dark : MoistureColors.light,
        isDark ? StatusColors.dark(scheme) : StatusColors.light(scheme),
      ],
      cardTheme: CardThemeData(
        color: scheme.surfaceContainerLow,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Radii.card),
        ),
      ),
      chipTheme: const ChipThemeData(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(Radii.chip)),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(),
      ),
    );
  }
}
