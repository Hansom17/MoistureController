import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'session.dart';

const _themeKey = 'theme_mode';
const _localeKey = 'locale';

final themeModeProvider = NotifierProvider<ThemeModeSetting, ThemeMode>(
  ThemeModeSetting.new,
);

class ThemeModeSetting extends Notifier<ThemeMode> {
  @override
  ThemeMode build() {
    final stored = ref.watch(sharedPreferencesProvider).getString(_themeKey);
    return ThemeMode.values.firstWhere(
      (m) => m.name == stored,
      orElse: () => ThemeMode.system,
    );
  }

  void set(ThemeMode mode) {
    state = mode;
    ref.read(sharedPreferencesProvider).setString(_themeKey, mode.name);
  }
}

const _valueModeKey = 'value_mode';

/// How moisture is shown: as a percentage or as the value the sensor measured (raw ADC counts).
enum ValueMode { percent, measured }

final valueModeProvider = NotifierProvider<ValueModeSetting, ValueMode>(ValueModeSetting.new);

class ValueModeSetting extends Notifier<ValueMode> {
  @override
  ValueMode build() {
    final stored = ref.watch(sharedPreferencesProvider).getString(_valueModeKey);
    return ValueMode.values.firstWhere((m) => m.name == stored, orElse: () => ValueMode.percent);
  }

  void toggle() {
    state = state == ValueMode.percent ? ValueMode.measured : ValueMode.percent;
    ref.read(sharedPreferencesProvider).setString(_valueModeKey, state.name);
  }
}

/// Null = follow the system language.
final localeProvider = NotifierProvider<LocaleSetting, Locale?>(
  LocaleSetting.new,
);

class LocaleSetting extends Notifier<Locale?> {
  @override
  Locale? build() {
    final code = ref.watch(sharedPreferencesProvider).getString(_localeKey);
    return code == null ? null : Locale(code);
  }

  void set(Locale? locale) {
    state = locale;
    final prefs = ref.read(sharedPreferencesProvider);
    locale == null
        ? prefs.remove(_localeKey)
        : prefs.setString(_localeKey, locale.languageCode);
  }
}
