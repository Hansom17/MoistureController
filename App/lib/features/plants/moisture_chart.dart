import 'dart:math';
import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../app/theme/app_colors.dart';
import '../../core/format.dart';
import '../../core/settings.dart';
import '../../data/models.dart';

/// Moisture line chart coloured with the moisture scale along the value axis
/// (App/specs.md Part B §2.5). Rule thresholds are drawn as dashed lines.
class MoistureChart extends StatelessWidget {
  const MoistureChart({
    super.key,
    required this.readings,
    required this.range,
    this.thresholds = const [],
    this.now,
    this.mode = ValueMode.percent,
  });

  final List<Reading> readings;
  final ChartRange range;
  final List<int> thresholds;

  /// [ValueMode.measured] plots the raw counts on a scale of their own (no percentage lines).
  final ValueMode mode;

  /// The right edge of the chart; the current time unless a test fixes it.
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    if (readings.isEmpty) {
      return SizedBox(height: 120, child: Center(child: Text(context.l10n.noReadings)));
    }
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final moisture = MoistureColors.of(context);
    final locale = Localizations.localeOf(context).toString();
    // The x axis always spans the whole selected range, so a few readings do not stretch over it.
    final start = (now ?? DateTime.now()).subtract(range.span);
    double x(DateTime t) => t.difference(start).inSeconds / 3600;

    final measured = mode == ValueMode.measured;
    final shown = measured ? readings.where((r) => r.raw != null).toList() : readings;
    if (shown.isEmpty) {
      return SizedBox(height: 120, child: Center(child: Text(context.l10n.noReadings)));
    }
    double valueOf(Reading r) => measured ? r.raw! : r.moisturePercent;
    final values = shown.map(valueOf);
    final lowest = values.reduce(min);
    final highest = values.reduce(max);
    final minV = lowest.round();
    final maxV = highest.round();
    // the raw scale follows the data: a little room, about four grid lines
    final pad = math.max(10.0, (highest - lowest) * 0.1);
    final yStep = math.max(10.0, ((highest - lowest + 2 * pad) / 4 / 10).ceilToDouble() * 10);

    final axisFormat = switch (range) {
      ChartRange.day => DateFormat.Hm(locale),
      ChartRange.week => DateFormat.E(locale),
      ChartRange.month => DateFormat.Md(locale),
      ChartRange.year => DateFormat.MMM(locale),
    };
    final spanH = range.span.inSeconds / 3600;
    final labelStyle = theme.textTheme.labelSmall?.copyWith(
      color: scheme.onSurfaceVariant,
    );

    return Semantics(
      label: measured ? context.l10n.chartSummaryRaw(minV, maxV) : context.l10n.chartSummary(minV, maxV),
      excludeSemantics: true,
      child: SizedBox(
        height: 220,
        child: LineChart(
          LineChartData(
            minY: measured ? (lowest - pad).floorToDouble() : 0,
            maxY: measured ? (highest + pad).ceilToDouble() : 100,
            minX: 0,
            maxX: spanH,
            gridData: FlGridData(
              drawVerticalLine: false,
              horizontalInterval: measured ? yStep : 25,
              getDrawingHorizontalLine: (_) =>
                  FlLine(color: scheme.outlineVariant, strokeWidth: 0.5),
            ),
            borderData: FlBorderData(show: false),
            titlesData: FlTitlesData(
              topTitles: const AxisTitles(),
              rightTitles: const AxisTitles(),
              leftTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  interval: measured ? yStep : 25,
                  reservedSize: measured ? 44 : 36,
                  getTitlesWidget: (v, _) =>
                      Text(measured ? '${v.round()}' : '${v.round()}%', style: labelStyle),
                ),
              ),
              bottomTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  interval: spanH / 4,
                  reservedSize: 24,
                  getTitlesWidget: (v, meta) {
                    if (v == meta.max || v == meta.min) return const SizedBox();
                    final t = start.add(Duration(minutes: (v * 60).round()));
                    return Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(axisFormat.format(t), style: labelStyle),
                    );
                  },
                ),
              ),
            ),
            extraLinesData: ExtraLinesData(
              horizontalLines: [
                if (!measured)
                  for (final t in thresholds)
                    HorizontalLine(
                    y: t.toDouble(),
                    color: scheme.outline,
                    strokeWidth: 1,
                    dashArray: [6, 4],
                    label: HorizontalLineLabel(
                      show: true,
                      alignment: Alignment.topRight,
                      style: labelStyle,
                      labelResolver: (line) => '${line.y.round()}%',
                    ),
                  ),
              ],
            ),
            lineTouchData: LineTouchData(
              touchTooltipData: LineTouchTooltipData(
                getTooltipColor: (_) => scheme.inverseSurface,
                getTooltipItems: (spots) => [
                  for (final s in spots)
                    LineTooltipItem(
                      '${s.y.round()}${measured ? '' : '%'}\n${DateFormat.MMMd(locale).add_Hm().format(start.add(Duration(minutes: (s.x * 60).round())))}',
                      TextStyle(color: scheme.onInverseSurface, fontSize: 12),
                    ),
                ],
              ),
            ),
            lineBarsData: [
              LineChartBarData(
                spots: [
                  for (final r in shown) FlSpot(x(r.at), valueOf(r)),
                ],
                isCurved: true,
                preventCurveOverShooting: true,
                barWidth: 3,
                dotData: const FlDotData(show: false),
                // fl_chart spans the gradient over the line's own bounds, so
                // sample the scale between the lowest and highest value.
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [
                    for (var i = 0; i <= 4; i++)
                      moisture.forPercent(lowest + (highest - lowest) * i / 4),
                  ],
                ),
                belowBarData: BarAreaData(
                  show: true,
                  color: moisture
                      .forPercent((lowest + highest) / 2)
                      .withValues(alpha: 0.12),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
