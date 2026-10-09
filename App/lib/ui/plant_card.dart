import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';
import '../app/theme/tokens.dart';
import '../core/format.dart';
import '../data/models.dart';
import 'moisture_gauge.dart';
import 'status_chip.dart';

/// Dashboard card for one plant (App/specs.md Part A §4, dashboard).
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
                        if (device?.linkQuality != null) _Signal(quality: device!.linkQuality!),
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

/// Zigbee link quality (0..255) as a small signal icon.
class _Signal extends StatelessWidget {
  const _Signal({required this.quality});

  final int quality;

  @override
  Widget build(BuildContext context) {
    final weak = quality < 60;
    final color = weak ? StatusColors.of(context).warning : Theme.of(context).colorScheme.onSurfaceVariant;
    final icon = switch (quality) {
      < 60 => Icons.signal_cellular_alt_1_bar,
      < 130 => Icons.signal_cellular_alt_2_bar,
      _ => Icons.signal_cellular_alt,
    };
    return Semantics(
      label: context.l10n.signalValue(quality),
      excludeSemantics: true,
      child: Icon(icon, size: 16, color: color),
    );
  }
}
