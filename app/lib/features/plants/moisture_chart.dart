import 'dart:math';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../app/theme/app_colors.dart';
import '../../core/format.dart';
import '../../data/models.dart';

/// Moisture line chart coloured with the moisture scale along the value axis
/// (Design_System.md §2.5). Rule thresholds are drawn as dashed lines.
class MoistureChart extends StatelessWidget {
  const MoistureChart({
    super.key,
    required this.readings,
    required this.range,
    this.thresholds = const [],
  });

  final List<Reading> readings;
  final ChartRange range;
  final List<int> thresholds;

  @override
  Widget build(BuildContext context) {
    if (readings.isEmpty) return const SizedBox(height: 200);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final moisture = MoistureColors.of(context);
    final locale = Localizations.localeOf(context).toString();
    final start = readings.first.at;
    double x(DateTime t) => t.difference(start).inMinutes / 60;

    final values = readings.map((r) => r.moisturePercent);
    final lowest = values.reduce(min);
    final highest = values.reduce(max);
    final minV = lowest.round();
    final maxV = highest.round();

    final axisFormat = switch (range) {
      ChartRange.day => DateFormat.Hm(locale),
      ChartRange.week => DateFormat.E(locale),
      ChartRange.month => DateFormat.Md(locale),
      ChartRange.year => DateFormat.MMM(locale),
    };
    final spanH = x(readings.last.at);
    final labelStyle = theme.textTheme.labelSmall?.copyWith(
      color: scheme.onSurfaceVariant,
    );

    return Semantics(
      label: context.l10n.chartSummary(minV, maxV),
      excludeSemantics: true,
      child: SizedBox(
        height: 220,
        child: LineChart(
          LineChartData(
            minY: 0,
            maxY: 100,
            minX: 0,
            maxX: spanH,
            gridData: FlGridData(
              drawVerticalLine: false,
              horizontalInterval: 25,
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
                  interval: 25,
                  reservedSize: 36,
                  getTitlesWidget: (v, _) =>
                      Text('${v.round()}%', style: labelStyle),
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
                      '${s.y.round()}%\n${DateFormat.MMMd(locale).add_Hm().format(start.add(Duration(minutes: (s.x * 60).round())))}',
                      TextStyle(color: scheme.onInverseSurface, fontSize: 12),
                    ),
                ],
              ),
            ),
            lineBarsData: [
              LineChartBarData(
                spots: [
                  for (final r in readings) FlSpot(x(r.at), r.moisturePercent),
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
