import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../core/permissions.dart';
import '../../core/session.dart';
import '../../data/models.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';
import '../../ui/plant_card.dart';
import '../plants/plant_detail_screen.dart' show readNow;
import '../plants/plant_editor.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return AppScope(
      builder: (context, user) => Consumer(
        builder: (context, ref, _) {
          final name = ref.watch(installationProvider).value?.name ?? '';
          return Scaffold(
            appBar: AppBar(
              title: Text(name.isEmpty ? context.l10n.appTitle : name),
              centerTitle: false,
            ),
            floatingActionButton: can(user.role, AppAction.editPlants)
                ? FloatingActionButton.extended(
                    onPressed: () => showPlantEditor(context, ref),
                    icon: const Icon(Icons.add),
                    label: Text(context.l10n.addPlant),
                  )
                : null,
            body: const Column(
              children: [
                GatewayBannerHost(),
                Expanded(child: _PlantGrid()),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _PlantGrid extends ConsumerWidget {
  const _PlantGrid();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final plants = ref.watch(plantsProvider);
    final devices = ref.watch(devicesProvider).value ?? const [];
    final byId = {for (final d in devices) d.id: d};
    final role = ref.watch(currentUserProviderRole);

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(devicesProvider);
        final _ = await ref.refresh(plantsProvider.future);
      },
      child: AsyncBody(
        value: plants,
        onRetry: () => ref.invalidate(plantsProvider),
        data: (plants) {
          if (plants.isEmpty) {
            final noDevices = devices.where((d) => !d.isNew).isEmpty;
            return ListView(
              children: [
                EmptyState(
                  icon: Icons.yard_outlined,
                  title: l.noPlantsTitle,
                  body: noDevices ? l.noPlantsNoDevices : l.noPlantsBody,
                  action: noDevices && can(role, AppAction.manageDevices)
                      ? FilledButton.icon(
                          onPressed: () => context.go('/devices/add'),
                          icon: const Icon(Icons.add),
                          label: Text(l.addDevice),
                        )
                      : null,
                ),
              ],
            );
          }
          // Cards keep their natural height so large text never clips.
          return LayoutBuilder(
            builder: (context, constraints) {
              const gap = Spacing.md;
              final width = constraints.maxWidth - 2 * Spacing.lg;
              final columns = ((width + gap) / (400 + gap)).floor().clamp(1, 4);
              final itemWidth = (width - gap * (columns - 1)) / columns;
              return ListView(
                padding: const EdgeInsets.fromLTRB(Spacing.lg, Spacing.lg, Spacing.lg, 96),
                children: [
                  Wrap(
                    spacing: gap,
                    runSpacing: gap,
                    children: [
                      for (final plant in plants)
                        SizedBox(
                          width: itemWidth,
                          child: PlantCard(
                            plant: plant,
                            device: byId[plant.deviceId],
                            hasPendingCommand: (ref.watch(commandsProvider(plant.id)).value ?? const <Command>[])
                                .any((c) => !c.state.isFinal),
                            onTap: () => context.go('/plants/${plant.id}'),
                            onReadNow: can(role, AppAction.identifyDevice) && (byId[plant.deviceId]?.reachable ?? false)
                                ? () => readNow(context, ref, byId[plant.deviceId]!)
                                : null,
                          ),
                        ),
                    ],
                  ),
                ],
              );
            },
          );
        },
      ),
    );
  }
}
