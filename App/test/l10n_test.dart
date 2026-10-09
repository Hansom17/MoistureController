import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The web build bundles Roboto and must not need a font from a CDN (the gateway may be offline;
/// App/specs.md Part A §2). A character Roboto lacks makes Flutter fetch a fallback font from the
/// internet on every frame that shows it, so texts may only use characters Roboto has.
void main() {
  const allowed = '—–…·§äöüÄÖÜß€°±×';

  for (final lang in ['en', 'de']) {
    test('app_$lang.arb only uses characters of the bundled font', () {
      final arb = jsonDecode(File('l10n/app_$lang.arb').readAsStringSync()) as Map<String, dynamic>;
      for (final MapEntry(:key, :value) in arb.entries) {
        if (value is! String || key.startsWith('@')) continue;
        for (final rune in value.runes) {
          final c = String.fromCharCode(rune);
          expect(rune < 128 || allowed.contains(c), isTrue, reason: '"$c" (U+${rune.toRadixString(16)}) in $key');
        }
      }
    });
  }

  test('both languages have the same keys', () {
    Set<String> keys(String lang) =>
        (jsonDecode(File('l10n/app_$lang.arb').readAsStringSync()) as Map<String, dynamic>)
            .keys
            .where((k) => !k.startsWith('@')) // placeholder metadata lives in the template only
            .toSet();
    expect(keys('de'), keys('en'));
  });
}
