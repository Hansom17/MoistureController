import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/tokens.dart';
import '../../core/format.dart';
import '../../core/household_data.dart';
import '../../data/models.dart';
import '../../ui/common.dart';
import '../../ui/household_scope.dart';
import '../../ui/status_chip.dart';
import '../dashboard/dashboard_screen.dart';

class DevicesScreen extends StatelessWidget {
  const DevicesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return HouseholdScope(
      builder: (context, household) => Consumer(
        builder: (context, ref, _) {
          final devices = ref.watch(devicesProvider(household.id));
          final banner = gatewayOfflineMessage(context, household);
          return Scaffold(
            appBar: AppBar(title: Text(l.navDevices)),
            body: Column(
              children: [
                ?(banner == null ? null : HouseholdBanner(message: banner)),
                Expanded(
                  child: RefreshIndicator(
                    onRefresh: () =>
                        ref.refresh(devicesProvider(household.id).future),
                    child: AsyncBody(
                      value: devices,
                      onRetry: () =>
                          ref.invalidate(devicesProvider(household.id)),
                      data: (devices) => devices.isEmpty
                          ? ListView(
                              children: [
                                EmptyState(
                                  icon: Icons.sensors,
                                  title: l.noDevices,
                                ),
                              ],
                            )
                          : ListView.separated(
                              padding: const EdgeInsets.all(Spacing.lg),
                              itemCount: devices.length,
                              separatorBuilder: (_, _) =>
                                  const SizedBox(height: Spacing.sm),
                              itemBuilder: (context, i) =>
                                  _DeviceTile(device: devices[i]),
                            ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _DeviceTile extends StatelessWidget {
  const _DeviceTile({required this.device});

  final Device device;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    );
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.go('/devices/${device.id}'),
        child: Padding(
          padding: const EdgeInsets.all(Spacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      device.name,
                      style: theme.textTheme.titleMedium,
                    ),
                  ),
                  const Icon(Icons.chevron_right),
                ],
              ),
              const SizedBox(height: Spacing.sm),
              Wrap(
                spacing: Spacing.sm,
                runSpacing: Spacing.xs,
                children: [
                  StatusChip.device(context, device, withLastSeen: true),
                  if (device.needsRepair)
                    StatusChip(
                      kind: StatusKind.warning,
                      icon: Icons.link_off,
                      label: context.l10n.deviceNeedsRepair,
                    ),
                  configSyncChip(context, device),
                ],
              ),
              const SizedBox(height: Spacing.sm),
              Text(
                [
                  l.batteryValue(device.batteryPercent),
                  l.signalValue(device.rssi),
                  l.firmwareValue(device.firmware),
                ].join(' · '),
                style: muted,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Desired vs. reported config state (App_Specs §7).
StatusChip configSyncChip(BuildContext context, Device device) {
  final l = context.l10n;
  return switch (device.configSync) {
    ConfigSync.inSync => StatusChip(
      kind: StatusKind.ok,
      label: l.configInSync,
      icon: Icons.sync,
    ),
    ConfigSync.pending => StatusChip(
      kind: StatusKind.pending,
      label: l.configPending(device.configRev + 1),
    ),
    ConfigSync.rejected => StatusChip(
      kind: StatusKind.error,
      label: l.configRejected,
      detail: device.configError,
    ),
  };
}
