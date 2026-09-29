import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/format.dart';
import '../../core/household_data.dart';
import '../../data/models.dart';
import '../../ui/common.dart';
import '../../ui/household_scope.dart';
import '../../ui/plant_card.dart';
import '../households/household_switcher.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return HouseholdScope(
      builder: (context, household) => Scaffold(
        appBar: AppBar(
          title: HouseholdSwitcherButton(current: household),
          centerTitle: false,
        ),
        body: Column(
          children: [
            if (gatewayOfflineMessage(context, household) case final message?)
              HouseholdBanner(message: message),
            Expanded(child: _PlantGrid(household: household)),
          ],
        ),
      ),
    );
  }
}

/// Banner text for households whose gateway is offline, else null.
String? gatewayOfflineMessage(BuildContext context, Household household) {
  final gateway = household.gateway;
  if (gateway == null || gateway.online) return null;
  final since = gateway.offlineSince;
  return context.l10n.gatewayOfflineBanner(
    since == null ? '—' : formatTime(context, since),
  );
}

class _PlantGrid extends ConsumerWidget {
  const _PlantGrid({required this.household});

  final Household household;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final plants = ref.watch(plantsProvider(household.id));
    final devices = ref.watch(devicesProvider(household.id)).value ?? const [];
    final byId = {for (final d in devices) d.id: d};

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(devicesProvider(household.id));
        final _ = await ref.refresh(plantsProvider(household.id).future);
      },
      child: AsyncBody(
        value: plants,
        onRetry: () => ref.invalidate(plantsProvider(household.id)),
        data: (plants) {
          if (plants.isEmpty) {
            return ListView(
              children: [
                EmptyState(
                  icon: Icons.yard_outlined,
                  title: l.noPlantsTitle,
                  body: l.noPlantsBody,
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
                padding: const EdgeInsets.all(Spacing.lg),
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
                            hasPendingCommand:
                                (ref
                                            .watch(
                                              commandsProvider((
                                                householdId: household.id,
                                                plantId: plant.id,
                                              )),
                                            )
                                            .value ??
                                        const <Command>[])
                                    .any((c) => !c.state.isFinal),
                            onTap: () => context.go('/plants/${plant.id}'),
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
