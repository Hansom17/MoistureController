import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/format.dart';
import '../../core/household_data.dart';
import '../../core/permissions.dart';
import '../../data/models.dart';
import '../../ui/common.dart';
import '../../ui/household_scope.dart';
import '../../ui/status_chip.dart';
import 'devices_screen.dart';

class DeviceDetailScreen extends StatelessWidget {
  const DeviceDetailScreen({super.key, required this.deviceId});

  final String deviceId;

  @override
  Widget build(BuildContext context) {
    return HouseholdScope(
      builder: (context, household) => Consumer(
        builder: (context, ref, _) {
          final devices = ref.watch(devicesProvider(household.id));
          final device = devices.value
              ?.where((d) => d.id == deviceId)
              .firstOrNull;
          return Scaffold(
            appBar: AppBar(title: Text(device?.name ?? '')),
            body: AsyncBody(
              value: devices,
              onRetry: () => ref.invalidate(devicesProvider(household.id)),
              data: (_) => device == null
                  ? const SizedBox()
                  : _DeviceBody(household: household, device: device),
            ),
          );
        },
      ),
    );
  }
}

class _DeviceBody extends ConsumerWidget {
  const _DeviceBody({required this.household, required this.device});

  final Household household;
  final Device device;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final role = household.role;

    Widget row(String label, String value) => ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      title: Text(label),
      trailing: Text(value, style: Theme.of(context).textTheme.bodyMedium),
    );

    Widget actionButton(
      DeviceAction action,
      IconData icon,
      String label,
      AppAction needs,
    ) => RoleGate(
      role: role,
      action: needs,
      builder: (context, allowed) => OutlinedButton.icon(
        icon: Icon(icon),
        label: Text(label),
        onPressed: allowed ? () => _send(context, ref, action) : null,
      ),
    );

    return ListView(
      padding: const EdgeInsets.all(Spacing.lg),
      children: [
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
        const SizedBox(height: Spacing.md),
        SectionCard(
          title: l.deviceDetails,
          child: Column(
            children: [
              row(l.board, device.board),
              row(l.firmware, device.firmware),
              row(l.battery, l.percentValue(device.batteryPercent)),
              row(l.signal, '${device.rssi} dBm'),
              row(l.wakeInterval, l.everyMinutes(device.wakeIntervalS ~/ 60)),
              row(l.nextExpected, formatTime(context, device.nextExpectedAt)),
            ],
          ),
        ),
        const SizedBox(height: Spacing.md),
        SectionCard(
          title: l.slots,
          child: Column(
            children: [
              for (final s in device.slots)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(
                    s.module == 'pump'
                        ? Icons.water_drop_outlined
                        : Icons.sensors,
                  ),
                  title: Text('${l.slotLabel(s.index)} · ${s.module}'),
                  subtitle: Text(
                    [
                      l.pinLabel(s.pin),
                      if (s.maxRunS != null) l.pumpLimit(s.maxRunS!),
                    ].join(' · '),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: Spacing.md),
        Wrap(
          spacing: Spacing.sm,
          runSpacing: Spacing.sm,
          children: [
            actionButton(
              DeviceAction.identify,
              Icons.lightbulb_outline,
              l.identify,
              AppAction.identifyDevice,
            ),
            actionButton(
              DeviceAction.serviceMode,
              Icons.build_outlined,
              l.serviceMode,
              AppAction.manageDevices,
            ),
            actionButton(
              DeviceAction.reboot,
              Icons.restart_alt,
              l.reboot,
              AppAction.manageDevices,
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _send(
    BuildContext context,
    WidgetRef ref,
    DeviceAction action,
  ) async {
    try {
      await ref
          .read(householdActionsProvider)
          .deviceAction(household.id, device.id, action);
      if (context.mounted) showSnackBar(context, context.l10n.deviceActionSent);
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}
