import 'dart:math';

import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';
import '../core/format.dart';

enum GaugeSize {
  small(48, 5, 13),
  medium(72, 7, 18),
  large(120, 10, 30);

  const GaugeSize(this.diameter, this.stroke, this.fontSize);

  final double diameter;
  final double stroke;
  final double fontSize;
}

/// Ring gauge filled with the moisture colour, always showing the number
/// (Design_System.md §2.3).
class MoistureGauge extends StatelessWidget {
  const MoistureGauge({
    super.key,
    required this.percent,
    this.size = GaugeSize.medium,
  });

  /// Null = no reading yet; shows "—" and an empty ring.
  final double? percent;
  final GaugeSize size;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final p = percent;
    final value = p?.round();
    return Semantics(
      label: value == null
          ? context.l10n.noReading
          : context.l10n.moistureSemantics(value),
      excludeSemantics: true,
      child: SizedBox.square(
        dimension: size.diameter,
        child: CustomPaint(
          painter: _RingPainter(
            fraction: p == null ? 0 : p.clamp(0, 100) / 100,
            color: MoistureColors.of(context).forPercent(p ?? 0),
            track: scheme.surfaceContainerHighest,
            stroke: size.stroke,
          ),
          child: Center(
            child: Text(
              value == null ? '—' : '$value%',
              style: TextStyle(
                fontSize: size.fontSize,
                fontWeight: FontWeight.w600,
                color: scheme.onSurface,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({
    required this.fraction,
    required this.color,
    required this.track,
    required this.stroke,
  });

  final double fraction;
  final Color color;
  final Color track;
  final double stroke;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = (Offset.zero & size).deflate(stroke / 2);
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(rect, 0, 2 * pi, false, paint..color = track);
    if (fraction > 0) {
      canvas.drawArc(
        rect,
        -pi / 2,
        2 * pi * fraction,
        false,
        paint..color = color,
      );
    }
  }

  @override
  bool shouldRepaint(_RingPainter old) =>
      old.fraction != fraction || old.color != color || old.track != track;
}
