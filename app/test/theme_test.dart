import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/app/theme/app_colors.dart';
import 'package:moisture_controller/app/theme/color_scheme.dart';

double contrast(Color a, Color b) {
  final la = a.computeLuminance(), lb = b.computeLuminance();
  return (max(la, lb) + 0.05) / (min(la, lb) + 0.05);
}

void main() {
  test('moisture scale hits the stops and clamps', () {
    const m = MoistureColors.light;
    expect(m.forPercent(0), m.stops[0]);
    expect(m.forPercent(50), m.stops[2]);
    expect(m.forPercent(100), m.stops[4]);
    expect(m.forPercent(-5), m.stops[0]);
    expect(m.forPercent(140), m.stops[4]);
  });

  // Guards the contrast claims in Design_System.md §2.3 / §2.4.
  for (final (name, scheme, moisture, status) in [
    (
      'light',
      AppColorSchemes.light,
      MoistureColors.light,
      StatusColors.light(AppColorSchemes.light),
    ),
    (
      'dark',
      AppColorSchemes.dark,
      MoistureColors.dark,
      StatusColors.dark(AppColorSchemes.dark),
    ),
  ]) {
    final surfaces = [
      scheme.surface,
      scheme.surfaceContainerLow,
      scheme.surfaceContainerHigh,
    ];
    test('$name: moisture stops ≥ 3:1 on surfaces', () {
      for (final c in moisture.stops) {
        for (final s in surfaces) {
          expect(contrast(c, s), greaterThanOrEqualTo(3), reason: '$c on $s');
        }
      }
    });
    test('$name: status chip text ≥ 4.5:1 on tinted page and card', () {
      for (final kind in StatusKind.values) {
        final c = status.forKind(kind);
        for (final s in surfaces.take(2)) {
          final chip = Color.alphaBlend(
            c.withValues(alpha: status.chipAlpha),
            s,
          );
          expect(
            contrast(c, chip),
            greaterThanOrEqualTo(4.5),
            reason: '$kind on $s',
          );
        }
      }
    });
  }
}
