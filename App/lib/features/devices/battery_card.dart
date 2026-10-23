import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';
import '../../ui/status_chip.dart';

/// Battery of a module: level, state, history and the calibration (App/specs.md Part A §10.1).
class BatteryCard extends ConsumerStatefulWidget {
  const BatteryCard({super.key, required this.device, required this.canCalibrate});

  final Device device;
  final bool canCalibrate;

  @override
  ConsumerState<BatteryCard> createState() => _BatteryCardState();
}

class _BatteryCardState extends ConsumerState<BatteryCard> {
  var _range = ChartRange.week;

  @override
  Widget build(BuildContext context) {
    final b = widget.device.battery;
    if (b == null) return const SizedBox.shrink();
    final l = context.l10n;
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);

    final (kind, stateLabel) = switch (b.state) {
      BatteryState.absent => (StatusKind.sleeping, l.batteryStateAbsent),
      BatteryState.ok => (StatusKind.ok, l.batteryStateOk),
      BatteryState.low => (StatusKind.warning, l.batteryStateLow),
      BatteryState.critical => (StatusKind.error, l.batteryStateCritical),
    };
    Widget row(String label, String value) => ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      title: Text(label),
      trailing: Text(value, style: theme.textTheme.bodyMedium),
    );

    final key = (deviceId: widget.device.id, range: _range);
    final history = b.present ? ref.watch(batteryHistoryProvider(key)) : null;
    final installation = ref.watch(installationProvider).value;
    final delta = (b.calPermille - 1000) / 10;

    return SectionCard(
      title: l.batteryTitle,
      trailing: widget.canCalibrate && b.present
          ? TextButton.icon(
              icon: const Icon(Icons.tune),
              label: Text(l.calibrateBattery),
              onPressed: () => _calibrate(context, b),
            )
          : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(alignment: Alignment.centerLeft, child: StatusChip(kind: kind, label: stateLabel)),
          if (b.present) ...[
            row(l.batteryVoltage, l.batteryVolts(b.volts.toStringAsFixed(2))),
            if (b.percent != null) row(l.batteryLevel, l.batteryPercent(b.percent!)),
            if (b.calibrated) Text(l.batteryCalibrated('${delta >= 0 ? '+' : ''}${delta.toStringAsFixed(1)} %'), style: muted),
            if (b.mv > 4100) Text(l.batteryChargingHint, style: muted),
            const SizedBox(height: Spacing.md),
            SegmentedButton<ChartRange>(
              showSelectedIcon: false,
              segments: [
                ButtonSegment(value: ChartRange.day, label: Text(l.range24h)),
                ButtonSegment(value: ChartRange.week, label: Text(l.range7d)),
                ButtonSegment(value: ChartRange.month, label: Text(l.range30d)),
              ],
              selected: {_range},
              onSelectionChanged: (s) => setState(() => _range = s.first),
            ),
            const SizedBox(height: Spacing.lg),
            AsyncBody(
              value: history!,
              onRetry: () => ref.invalidate(batteryHistoryProvider(key)),
              data: (points) => BatteryChart(
                points: points,
                range: _range,
                low: installation?.batteryLowMv ?? 3600,
                critical: installation?.batteryCriticalMv ?? 3400,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _calibrate(BuildContext context, Battery b) async {
    final l = context.l10n;
    final value = await showDialog<int>(
      context: context,
      builder: (context) => _CalibrateDialog(volts: b.volts),
    );
    if (value == null || !context.mounted) return;
    try {
      await ref.read(actionsProvider).calibrateBattery(widget.device.id, value);
      if (context.mounted) showSnackBar(context, l.batteryCalibrationSent);
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}

/// Asks for the multimeter reading; pops the value in millivolts. Owns its controller, so it is disposed
/// only after the closing animation.
class _CalibrateDialog extends StatefulWidget {
  const _CalibrateDialog({required this.volts});

  final double volts;

  @override
  State<_CalibrateDialog> createState() => _CalibrateDialogState();
}

class _CalibrateDialogState extends State<_CalibrateDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final v = double.tryParse(_controller.text.trim().replaceAll(',', '.'));
    if (v != null && v > 1 && v < 6) Navigator.pop(context, (v * 1000).round());
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AlertDialog(
      title: Text(l.calibrateBattery),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l.calibrateBatteryBody(widget.volts.toStringAsFixed(2))),
          const SizedBox(height: Spacing.md),
          TextField(
            controller: _controller,
            autofocus: true,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(labelText: l.measuredVolts, suffixText: 'V'),
            onSubmitted: (_) => _submit(),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(l.cancel)),
        FilledButton(onPressed: _submit, child: Text(l.calibrate)),
      ],
    );
  }
}

/// Battery voltage over time with the two thresholds as dashed lines.
class BatteryChart extends StatelessWidget {
  const BatteryChart({
    super.key,
    required this.points,
    required this.range,
    required this.low,
    required this.critical,
    this.now,
  });

  final List<BatteryPoint> points;
  final ChartRange range;
  final int low;
  final int critical;
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) {
      return SizedBox(height: 120, child: Center(child: Text(context.l10n.batteryNoData)));
    }
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final status = StatusColors.of(context);
    final locale = Localizations.localeOf(context).toString();
    final start = (now ?? DateTime.now()).subtract(range.span);
    double x(DateTime t) => t.difference(start).inSeconds / 3600;
    final spanH = range.span.inSeconds / 3600;
    final labelStyle = theme.textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant);
    final axisFormat = switch (range) {
      ChartRange.day => DateFormat.Hm(locale),
      ChartRange.week => DateFormat.E(locale),
      _ => DateFormat.Md(locale),
    };
    final mvs = points.map((p) => p.mv);
    final minY = ((mvs.reduce((a, b) => a < b ? a : b) < critical ? mvs.reduce((a, b) => a < b ? a : b) : critical) - 100) ~/ 100 * 100.0;
    final maxY = ((mvs.reduce((a, b) => a > b ? a : b)) + 100) ~/ 100 * 100.0 + 100;

    HorizontalLine line(int mv, Color color) => HorizontalLine(
      y: mv.toDouble(),
      color: color,
      strokeWidth: 1,
      dashArray: [6, 4],
      label: HorizontalLineLabel(show: true, alignment: Alignment.topRight, style: labelStyle, labelResolver: (_) => '${(mv / 1000).toStringAsFixed(2)} V'),
    );

    return SizedBox(
      height: 200,
      child: LineChart(
        LineChartData(
          minY: minY,
          maxY: maxY,
          minX: 0,
          maxX: spanH,
          gridData: FlGridData(
            drawVerticalLine: false,
            horizontalInterval: 200,
            getDrawingHorizontalLine: (_) => FlLine(color: scheme.outlineVariant, strokeWidth: 0.5),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(),
            rightTitles: const AxisTitles(),
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                interval: 200,
                reservedSize: 44,
                getTitlesWidget: (v, _) => Text('${(v / 1000).toStringAsFixed(1)} V', style: labelStyle),
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
            horizontalLines: [line(low, status.warning), line(critical, status.error)],
          ),
          lineBarsData: [
            LineChartBarData(
              spots: [for (final p in points) FlSpot(x(p.at), p.mv.toDouble())],
              isCurved: true,
              preventCurveOverShooting: true,
              barWidth: 3,
              color: scheme.primary,
              dotData: const FlDotData(show: false),
            ),
          ],
        ),
      ),
    );
  }
}
