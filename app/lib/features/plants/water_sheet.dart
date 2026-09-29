import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../ui/common.dart';

/// "Water now" with a seconds picker within the pump's limit (App_Specs §4).
Future<void> showWaterSheet(
  BuildContext context,
  WidgetRef ref,
  Household household,
  Plant plant,
) async {
  final seconds = await showModalBottomSheet<int>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (context) => _WaterSheet(plant: plant),
  );
  if (seconds == null || !context.mounted) return;

  final l = context.l10n;
  try {
    await ref
        .read(householdActionsProvider)
        .waterNow(household.id, plant.id, seconds);
    if (!context.mounted) return;
    final gatewayOffline =
        household.gateway != null && !household.gateway!.online;
    showSnackBar(
      context,
      gatewayOffline ? l.waterQueuedGatewayOffline : l.waterQueued,
    );
  } catch (e) {
    if (context.mounted) showErrorSnackBar(context, e);
  }
}

class _WaterSheet extends StatefulWidget {
  const _WaterSheet({required this.plant});

  final Plant plant;

  @override
  State<_WaterSheet> createState() => _WaterSheetState();
}

class _WaterSheetState extends State<_WaterSheet> {
  late double _seconds = widget.plant.maxRunS < 10
      ? widget.plant.maxRunS.toDouble()
      : 10;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final max = widget.plant.maxRunS;
    final value = _seconds.round();

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          Spacing.xl,
          0,
          Spacing.xl,
          Spacing.xl,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              l.waterSheetTitle(widget.plant.name),
              style: theme.textTheme.titleLarge,
            ),
            const SizedBox(height: Spacing.sm),
            Text(
              l.waterSheetHint,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: Spacing.xl),
            Center(
              child: Text(
                l.secondsValue(value),
                style: theme.textTheme.displaySmall?.copyWith(
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
            Slider(
              value: _seconds,
              min: 1,
              max: max.toDouble(),
              divisions: max > 1 ? max - 1 : null,
              label: l.secondsValue(value),
              onChanged: (v) => setState(() => _seconds = v),
            ),
            Text(
              l.pumpLimit(max),
              textAlign: TextAlign.end,
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: Spacing.lg),
            FilledButton.icon(
              icon: const Icon(Icons.water_drop),
              label: Text(l.waterFor(value)),
              onPressed: () => Navigator.pop(context, value),
            ),
          ],
        ),
      ),
    );
  }
}
