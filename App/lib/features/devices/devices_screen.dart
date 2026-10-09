import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/tokens.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../core/permissions.dart';
import '../../data/models.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';
import '../../ui/status_chip.dart';

class DevicesScreen extends StatelessWidget {
  const DevicesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AppScope(
      builder: (context, user) => Consumer(
        builder: (context, ref, _) {
          final devices = ref.watch(devicesProvider);
          return Scaffold(
            appBar: AppBar(title: Text(l.navDevices)),
            floatingActionButton: can(user.role, AppAction.manageDevices)
                ? FloatingActionButton.extended(
                    onPressed: () => context.go('/devices/add'),
                    icon: const Icon(Icons.add),
                    label: Text(l.addDevice),
                  )
                : null,
            body: Column(
              children: [
                const GatewayBannerHost(),
                Expanded(
                  child: RefreshIndicator(
                    onRefresh: () => ref.refresh(devicesProvider.future),
                    child: AsyncBody(
                      value: devices,
                      onRetry: () => ref.invalidate(devicesProvider),
                      data: (devices) => devices.isEmpty
                          ? ListView(children: [EmptyState(icon: Icons.sensors, title: l.noDevices, body: l.noDevicesBody)])
                          : ListView.separated(
                              padding: const EdgeInsets.fromLTRB(Spacing.lg, Spacing.lg, Spacing.lg, 96),
                              itemCount: devices.length,
                              separatorBuilder: (_, _) => const SizedBox(height: Spacing.sm),
                              itemBuilder: (context, i) => _DeviceTile(device: devices[i]),
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
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
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
                  Expanded(child: Text(device.name, style: theme.textTheme.titleMedium)),
                  const Icon(Icons.chevron_right),
                ],
              ),
              const SizedBox(height: Spacing.sm),
              Wrap(
                spacing: Spacing.sm,
                runSpacing: Spacing.xs,
                children: [
                  StatusChip.device(context, device, withLastSeen: true),
                  if (!device.isNew) configSyncChip(context, device),
                ],
              ),
              const SizedBox(height: Spacing.sm),
              Text(
                [
                  if (device.linkQuality != null) l.signalValue(device.linkQuality!),
                  if (device.firmware != null) l.firmwareValue(device.firmware!),
                  if (device.board != null) device.board!,
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

/// Desired vs. reported config state (App/specs.md Part A §7).
StatusChip configSyncChip(BuildContext context, Device device) {
  final l = context.l10n;
  return switch (device.configSync) {
    ConfigSync.inSync => StatusChip(kind: StatusKind.ok, label: l.configInSync, icon: Icons.sync),
    ConfigSync.pending => StatusChip(kind: StatusKind.pending, label: l.configPending(device.desiredRev)),
    ConfigSync.rejected => StatusChip(kind: StatusKind.error, label: l.configRejected, detail: device.configError),
  };
}
