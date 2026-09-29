import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';
import '../app/theme/tokens.dart';
import '../core/format.dart';
import '../data/models.dart';
import 'moisture_gauge.dart';
import 'status_chip.dart';

/// Dashboard card for one plant (App_Specs §4, dashboard).
class PlantCard extends StatelessWidget {
  const PlantCard({
    super.key,
    required this.plant,
    this.device,
    this.hasPendingCommand = false,
    this.onTap,
  });

  final Plant plant;
  final Device? device;
  final bool hasPendingCommand;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    );
    final (trendIcon, trendLabel) = switch (plant.trend) {
      Trend.falling => (Icons.trending_down, l.trendFalling),
      Trend.steady => (Icons.trending_flat, l.trendSteady),
      Trend.rising => (Icons.trending_up, l.trendRising),
    };

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(Spacing.lg),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              MoistureGauge(percent: plant.moisturePercent),
              const SizedBox(width: Spacing.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(plant.name, style: theme.textTheme.titleMedium),
                    const SizedBox(height: Spacing.xs),
                    Row(
                      children: [
                        Icon(
                          trendIcon,
                          size: 16,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        const SizedBox(width: Spacing.xs),
                        Flexible(
                          child: Text(
                            plant.lastReadingAt == null
                                ? l.noReading
                                : '$trendLabel · ${formatAgo(l, plant.lastReadingAt!)}',
                            style: muted,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: Spacing.sm),
                    Wrap(
                      spacing: Spacing.sm,
                      runSpacing: Spacing.xs,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        if (device != null) StatusChip.device(context, device!),
                        if (hasPendingCommand)
                          StatusChip(
                            kind: StatusKind.pending,
                            label: l.pendingCommand,
                          ),
                        if (device != null)
                          _Battery(percent: device!.batteryPercent),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Battery extends StatelessWidget {
  const _Battery({required this.percent});

  final int percent;

  @override
  Widget build(BuildContext context) {
    final low = percent < 20;
    final color = low
        ? StatusColors.of(context).warning
        : Theme.of(context).colorScheme.onSurfaceVariant;
    final icon = switch (percent) {
      < 20 => Icons.battery_alert,
      < 50 => Icons.battery_3_bar,
      < 80 => Icons.battery_5_bar,
      _ => Icons.battery_full,
    };
    return Semantics(
      label: context.l10n.batteryValue(percent),
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: color),
          Text(
            '$percent%',
            style: Theme.of(
              context,
            ).textTheme.labelMedium?.copyWith(color: color),
          ),
        ],
      ),
    );
  }
}
