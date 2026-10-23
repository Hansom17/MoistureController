import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';
import '../core/format.dart';
import '../data/models.dart';
import 'status_chip.dart';

/// "about 72 %" with the colour of the battery state. Nothing at all without a cell (USB only): the module
/// then has no battery to talk about (App/specs.md Part A §10.1).
class BatteryChip extends StatelessWidget {
  const BatteryChip({super.key, required this.device});

  final Device device;

  @override
  Widget build(BuildContext context) {
    final b = device.battery;
    if (b == null || !b.present) return const SizedBox.shrink();
    final l = context.l10n;
    final (kind, icon) = switch (b.state) {
      BatteryState.critical => (StatusKind.error, Icons.battery_alert),
      BatteryState.low => (StatusKind.warning, Icons.battery_2_bar),
      _ => (StatusKind.ok, Icons.battery_full),
    };
    return StatusChip(
      kind: kind,
      icon: icon,
      label: b.percent == null ? '—' : l.batteryPercent(b.percent!),
    );
  }
}
