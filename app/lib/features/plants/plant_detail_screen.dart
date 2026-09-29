import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/format.dart';
import '../../core/household_data.dart';
import '../../core/permissions.dart';
import '../../data/models.dart';
import '../../ui/command_state_tile.dart';
import '../../ui/common.dart';
import '../../ui/household_scope.dart';
import '../../ui/moisture_gauge.dart';
import '../../ui/status_chip.dart';
import '../dashboard/dashboard_screen.dart';
import 'moisture_chart.dart';
import 'rule_editor.dart';
import 'water_sheet.dart';

class PlantDetailScreen extends StatelessWidget {
  const PlantDetailScreen({super.key, required this.plantId});

  final String plantId;

  @override
  Widget build(BuildContext context) {
    return HouseholdScope(
      builder: (context, household) => Consumer(
        builder: (context, ref, _) {
          final key = (householdId: household.id, plantId: plantId);
          final plant = ref.watch(plantProvider(key));
          return Scaffold(
            appBar: AppBar(title: Text(plant.value?.name ?? '')),
            body: AsyncBody(
              value: plant,
              onRetry: () => ref.invalidate(plantsProvider(household.id)),
              data: (plant) => _PlantBody(household: household, plant: plant),
            ),
          );
        },
      ),
    );
  }
}

class _PlantBody extends ConsumerWidget {
  const _PlantBody({required this.household, required this.plant});

  final Household household;
  final Plant plant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final banner = gatewayOfflineMessage(context, household);
    final overview = _Overview(household: household, plant: plant);
    final history = _History(household: household, plant: plant);
    final commands = _Commands(household: household, plant: plant);
    final rules = _Rules(household: household, plant: plant);

    return Column(
      children: [
        ?(banner == null ? null : HouseholdBanner(message: banner)),
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              const gap = SizedBox(height: Spacing.md, width: Spacing.md);
              if (constraints.maxWidth < Breakpoints.expanded) {
                return ListView(
                  padding: const EdgeInsets.all(Spacing.lg),
                  children: [overview, gap, history, gap, commands, gap, rules],
                );
              }
              // Two columns on tablets and desktop web (App_Specs §9).
              return SingleChildScrollView(
                padding: const EdgeInsets.all(Spacing.lg),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      flex: 3,
                      child: Column(children: [overview, gap, history]),
                    ),
                    gap,
                    Expanded(
                      flex: 2,
                      child: Column(children: [commands, gap, rules]),
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _Overview extends ConsumerWidget {
  const _Overview({required this.household, required this.plant});

  final Household household;
  final Plant plant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final devices = ref.watch(devicesProvider(household.id)).value ?? const [];
    final device = devices.where((d) => d.id == plant.deviceId).firstOrNull;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Spacing.lg),
        child: Row(
          children: [
            MoistureGauge(
              percent: plant.moisturePercent,
              size: GaugeSize.large,
            ),
            const SizedBox(width: Spacing.xl),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    plant.lastReadingAt == null
                        ? l.noReading
                        : l.lastReading(formatAgo(l, plant.lastReadingAt!)),
                    style: theme.textTheme.bodyMedium,
                  ),
                  const SizedBox(height: Spacing.sm),
                  if (device != null) ...[
                    Text(
                      device.name,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: Spacing.xs),
                    StatusChip.device(context, device, withLastSeen: true),
                  ],
                  const SizedBox(height: Spacing.lg),
                  if (plant.hasPump)
                    RoleGate(
                      role: household.role,
                      action: AppAction.water,
                      builder: (context, allowed) => FilledButton.icon(
                        icon: const Icon(Icons.water_drop),
                        label: Text(l.waterNow),
                        onPressed: allowed
                            ? () =>
                                  showWaterSheet(context, ref, household, plant)
                            : null,
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _History extends ConsumerStatefulWidget {
  const _History({required this.household, required this.plant});

  final Household household;
  final Plant plant;

  @override
  ConsumerState<_History> createState() => _HistoryState();
}

class _HistoryState extends ConsumerState<_History> {
  var _range = ChartRange.day;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final key = (
      householdId: widget.household.id,
      plantId: widget.plant.id,
      range: _range,
    );
    final readings = ref.watch(readingsProvider(key));
    final rules =
        ref
            .watch(
              rulesProvider((
                householdId: widget.household.id,
                plantId: widget.plant.id,
              )),
            )
            .value ??
        const [];

    return SectionCard(
      title: l.historyTitle,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SegmentedButton<ChartRange>(
            showSelectedIcon: false,
            segments: [
              ButtonSegment(value: ChartRange.day, label: Text(l.range24h)),
              ButtonSegment(value: ChartRange.week, label: Text(l.range7d)),
              ButtonSegment(value: ChartRange.month, label: Text(l.range30d)),
              ButtonSegment(value: ChartRange.year, label: Text(l.range1y)),
            ],
            selected: {_range},
            onSelectionChanged: (s) => setState(() => _range = s.first),
          ),
          const SizedBox(height: Spacing.lg),
          AsyncBody(
            value: readings,
            onRetry: () => ref.invalidate(readingsProvider(key)),
            data: (readings) => MoistureChart(
              readings: readings,
              range: _range,
              thresholds: [
                for (final r in rules)
                  if (r.enabled) r.belowPercent,
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Commands extends ConsumerWidget {
  const _Commands({required this.household, required this.plant});

  final Household household;
  final Plant plant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final key = (householdId: household.id, plantId: plant.id);
    final commands = ref.watch(commandsProvider(key));
    final canCancel = can(household.role, AppAction.water);

    return SectionCard(
      title: l.commandsTitle,
      child: AsyncBody(
        value: commands,
        onRetry: () => ref.invalidate(commandsProvider(key)),
        data: (commands) => commands.isEmpty
            ? Text(l.noCommands)
            : Column(
                children: [
                  for (final c in commands.take(10))
                    CommandStateTile(
                      command: c,
                      onCancel: canCancel
                          ? () => _cancel(context, ref, c)
                          : null,
                    ),
                ],
              ),
      ),
    );
  }

  Future<void> _cancel(BuildContext context, WidgetRef ref, Command c) async {
    final l = context.l10n;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l.cancelCommand),
        content: Text(l.cancelCommandHint),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(l.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(l.cancelCommand),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(householdActionsProvider).cancelCommand(household.id, c);
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}

class _Rules extends ConsumerWidget {
  const _Rules({required this.household, required this.plant});

  final Household household;
  final Plant plant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final key = (householdId: household.id, plantId: plant.id);
    final rules = ref.watch(rulesProvider(key));
    final allowed = can(household.role, AppAction.editRules);

    return SectionCard(
      title: l.rulesTitle,
      trailing: allowed
          ? IconButton(
              tooltip: l.addRule,
              icon: const Icon(Icons.add),
              onPressed: () => showRuleEditor(context, ref, household, plant),
            )
          : null,
      child: AsyncBody(
        value: rules,
        onRetry: () => ref.invalidate(rulesProvider(key)),
        data: (rules) => rules.isEmpty
            ? Text(l.noRules)
            : Column(
                children: [
                  for (final r in rules)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.rule),
                      title: Text(
                        l.ruleSummary(
                          r.belowPercent,
                          r.waterSeconds,
                          r.minIntervalHours,
                        ),
                      ),
                      onTap: allowed
                          ? () => showRuleEditor(
                              context,
                              ref,
                              household,
                              plant,
                              rule: r,
                            )
                          : null,
                      trailing: Switch(
                        value: r.enabled,
                        onChanged: allowed
                            ? (v) => ref
                                  .read(householdActionsProvider)
                                  .saveRule(
                                    household.id,
                                    r.copyWith(enabled: v),
                                  )
                                  .catchError((Object e) {
                                    if (context.mounted) {
                                      showErrorSnackBar(context, e);
                                    }
                                  })
                            : null,
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}
