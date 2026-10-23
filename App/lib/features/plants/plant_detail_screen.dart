import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/format.dart';
import '../../core/app_data.dart';
import '../../core/permissions.dart';
import '../../data/models.dart';
import '../../ui/command_state_tile.dart';
import '../../ui/common.dart';
import '../../ui/app_scope.dart';
import '../../ui/moisture_gauge.dart';
import '../../ui/status_chip.dart';
import 'plant_editor.dart';
import 'moisture_chart.dart';
import 'rule_editor.dart';
import 'water_sheet.dart';

class PlantDetailScreen extends StatelessWidget {
  const PlantDetailScreen({super.key, required this.plantId});

  final String plantId;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      builder: (context, user) => Consumer(
        builder: (context, ref, _) {
          final plant = ref.watch(plantProvider(plantId));
          return Scaffold(
            appBar: AppBar(
              title: Text(plant.value?.name ?? ''),
              actions: [
                if (plant.value != null && can(user.role, AppAction.editPlants))
                  IconButton(
                    tooltip: context.l10n.editPlant,
                    icon: const Icon(Icons.edit_outlined),
                    onPressed: () async {
                      await showPlantEditor(context, ref, plant: plant.value);
                      final stillThere = (await ref.read(plantsProvider.future)).any((p) => p.id == plantId);
                      if (!stillThere && context.mounted) context.go('/plants');
                    },
                  ),
              ],
            ),
            body: AsyncBody(
              value: plant,
              onRetry: () => ref.invalidate(plantsProvider),
              data: (plant) => _PlantBody(role: user.role, plant: plant),
            ),
          );
        },
      ),
    );
  }
}

class _PlantBody extends ConsumerWidget {
  const _PlantBody({required this.role, required this.plant});

  final Role role;
  final Plant plant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overview = _Overview(role: role, plant: plant);
    final history = _History(plant: plant);
    final commands = _Commands(role: role, plant: plant);
    final rules = _Rules(role: role, plant: plant);

    return Column(
      children: [
        const GatewayBannerHost(),
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
              // Two columns on tablets and desktop web (App/specs.md Part A §9).
              return SingleChildScrollView(
                padding: const EdgeInsets.all(Spacing.lg),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(flex: 3, child: Column(children: [overview, gap, history])),
                    gap,
                    Expanded(flex: 2, child: Column(children: [commands, gap, rules])),
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
  const _Overview({required this.role, required this.plant});

  final Role role;
  final Plant plant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final devices = ref.watch(devicesProvider).value ?? const [];
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
                      role: role,
                      action: AppAction.water,
                      builder: (context, allowed) => FilledButton.icon(
                        icon: const Icon(Icons.water_drop),
                        label: Text(l.waterNow),
                        onPressed: allowed
                            ? () => showWaterSheet(
                                context,
                                ref,
                                plant,
                                deviceOffline: device != null && !device.reachable,
                                batteryCritical: device?.battery?.state == BatteryState.critical,
                              )
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
  const _History({required this.plant});

  final Plant plant;

  @override
  ConsumerState<_History> createState() => _HistoryState();
}

class _HistoryState extends ConsumerState<_History> {
  var _range = ChartRange.day;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final key = (plantId: widget.plant.id, range: _range);
    final readings = ref.watch(readingsProvider(key));
    final rules = ref.watch(rulesProvider(widget.plant.id)).value ?? const [];

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
  const _Commands({required this.role, required this.plant});

  final Role role;
  final Plant plant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final commands = ref.watch(commandsProvider(plant.id));
    final devices = ref.watch(devicesProvider).value ?? const [];
    final canCancel = can(role, AppAction.water);

    return SectionCard(
      title: l.commandsTitle,
      child: AsyncBody(
        value: commands,
        onRetry: () => ref.invalidate(commandsProvider(plant.id)),
        data: (commands) => commands.isEmpty
            ? Text(l.noCommands)
            : Column(
                children: [
                  for (final c in commands.take(10))
                    CommandStateTile(
                      command: c,
                      deviceOffline: devices.any((d) => d.id == c.deviceId && !d.reachable),
                      onCancel: canCancel ? () => _cancel(context, ref, c) : null,
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
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(l.cancel)),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(l.cancelCommand)),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(actionsProvider).cancelCommand(c);
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}

class _Rules extends ConsumerWidget {
  const _Rules({required this.role, required this.plant});

  final Role role;
  final Plant plant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final rules = ref.watch(rulesProvider(plant.id));
    final allowed = can(role, AppAction.editRules) && plant.hasPump;

    return SectionCard(
      title: l.rulesTitle,
      trailing: allowed
          ? IconButton(
              tooltip: l.addRule,
              icon: const Icon(Icons.add),
              onPressed: () => showRuleEditor(context, ref, plant),
            )
          : null,
      child: AsyncBody(
        value: rules,
        onRetry: () => ref.invalidate(rulesProvider(plant.id)),
        data: (rules) => rules.isEmpty
            ? Text(plant.hasPump ? l.noRules : l.noRulesNoPump)
            : Column(
                children: [
                  for (final r in rules)
                    _RuleTile(role: role, plant: plant, rule: r, allowed: allowed),
                ],
              ),
      ),
    );
  }
}

class _RuleTile extends ConsumerWidget {
  const _RuleTile({required this.role, required this.plant, required this.rule, required this.allowed});

  final Role role;
  final Plant plant;
  final Rule rule;
  final bool allowed;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final r = rule;
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      shape: const Border(),
      collapsedShape: const Border(),
      leading: const Icon(Icons.rule),
      title: Text(l.ruleSummary(r.belowPercent, r.waterSeconds, r.cooldownHours)),
      subtitle: Text(
        [
          l.ruleMaxPerDayValue(r.maxPerDay),
          if (r.quietFrom != null) l.ruleQuietValue(r.quietFrom!, r.quietTo ?? ''),
        ].join(' · '),
      ),
      trailing: Switch(
        value: r.enabled,
        onChanged: allowed
            ? (v) => ref.read(actionsProvider).saveRule(r.copyWith(enabled: v)).catchError((Object e) {
                if (context.mounted) showErrorSnackBar(context, e);
              })
            : null,
      ),
      children: [
        if (allowed)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              icon: const Icon(Icons.edit_outlined),
              label: Text(l.editRule),
              onPressed: () => showRuleEditor(context, ref, plant, rule: r),
            ),
          ),
        Consumer(
          builder: (context, ref, _) {
            final ex = ref.watch(ruleExecutionsProvider((plantId: plant.id, ruleId: r.id)));
            return AsyncBody(
              value: ex,
              onRetry: () => ref.invalidate(ruleExecutionsProvider((plantId: plant.id, ruleId: r.id))),
              data: (list) => list.isEmpty
                  ? Text(l.noExecutions)
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(l.executionsTitle, style: Theme.of(context).textTheme.titleSmall),
                        for (final e in list.take(8))
                          ListTile(
                            dense: true,
                            contentPadding: EdgeInsets.zero,
                            leading: Icon(e.decision == 'water' ? Icons.water_drop_outlined : Icons.remove_circle_outline),
                            title: Text(e.decision == 'water' ? l.executionWatered : l.executionSkipped(skipReasonLabel(l, e.skipReason))),
                            subtitle: Text(formatAgo(l, e.at)),
                          ),
                      ],
                    ),
            );
          },
        ),
      ],
    );
  }
}
