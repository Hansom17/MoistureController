import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../core/permissions.dart';
import '../../data/models.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';
import '../../ui/reauth.dart';
import '../../ui/status_chip.dart';
import 'devices_screen.dart';

class DeviceDetailScreen extends StatelessWidget {
  const DeviceDetailScreen({super.key, required this.deviceId});

  final String deviceId;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      builder: (context, user) => Consumer(
        builder: (context, ref, _) {
          final devices = ref.watch(devicesProvider);
          final device = devices.value?.where((d) => d.id == deviceId).firstOrNull;
          return Scaffold(
            appBar: AppBar(title: Text(device?.name ?? '')),
            body: AsyncBody(
              value: devices,
              onRetry: () => ref.invalidate(devicesProvider),
              data: (_) => device == null ? const SizedBox() : _DeviceBody(role: user.role, device: device),
            ),
          );
        },
      ),
    );
  }
}

class _DeviceBody extends ConsumerWidget {
  const _DeviceBody({required this.role, required this.device});

  final Role role;
  final Device device;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final canManage = can(role, AppAction.manageDevices);

    Widget row(String label, String value) => ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      title: Text(label),
      trailing: Text(value, style: Theme.of(context).textTheme.bodyMedium),
    );

    Widget actionButton(DeviceAction action, IconData icon, String label, AppAction needs) => RoleGate(
      role: role,
      action: needs,
      builder: (context, allowed) => OutlinedButton.icon(
        icon: Icon(icon),
        label: Text(label),
        onPressed: allowed ? () => _send(context, ref, action) : null,
      ),
    );

    final d = device.diagnostics;
    String diag(String key, {String Function(Object)? fmt}) {
      final v = d[key];
      return v == null ? '—' : (fmt?.call(v) ?? '$v');
    }

    return ListView(
      padding: const EdgeInsets.all(Spacing.lg),
      children: [
        Wrap(
          spacing: Spacing.sm,
          runSpacing: Spacing.xs,
          children: [
            StatusChip.device(context, device, withLastSeen: true),
            if (!device.isNew) configSyncChip(context, device),
          ],
        ),
        if (device.status == DeviceStatus.safeMode) ...[
          const SizedBox(height: Spacing.md),
          SectionCard(
            title: l.safeModeTitle,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l.safeModeBody(device.safeReason ?? '—')),
                const SizedBox(height: Spacing.md),
                actionButton(DeviceAction.clearSafeMode, Icons.shield_outlined, l.clearSafeMode, AppAction.manageDevices),
              ],
            ),
          ),
        ],
        const SizedBox(height: Spacing.md),
        SectionCard(
          title: l.deviceDetails,
          child: Column(
            children: [
              row(l.board, device.board ?? '—'),
              row(l.firmware, device.firmware ?? '—'),
              row(l.signal, device.linkQuality == null ? '—' : '${device.linkQuality}'),
              row(l.lastSeenLabel, device.lastSeen == null ? '—' : formatAgo(l, device.lastSeen!)),
              row(l.configRevision, '${device.reportedRev ?? '—'} / ${device.desiredRev}'),
            ],
          ),
        ),
        const SizedBox(height: Spacing.md),
        SectionCard(
          title: l.diagnostics,
          child: Column(
            children: [
              row(l.diagUptime, diag('uptime_s', fmt: (v) => formatDuration(l, Duration(seconds: (v as num).toInt())))),
              row(l.diagBootReason, diag('boot_reason')),
              row(l.diagResets, diag('reset_count')),
              row(l.diagRejoins, diag('rejoin_count')),
              row(l.diagLastError, diag('last_error')),
              row(l.diagFreeHeap, diag('free_heap', fmt: (v) => '${((v as num) / 1024).round()} kB')),
            ],
          ),
        ),
        const SizedBox(height: Spacing.md),
        SectionCard(
          title: l.slots,
          trailing: canManage && !device.isNew
              ? TextButton.icon(
                  icon: const Icon(Icons.tune),
                  label: Text(l.editConfig),
                  onPressed: () => context.go('/devices/${device.id}/config'),
                )
              : null,
          child: device.slots.isEmpty
              ? Text(l.noSlots)
              : Column(
                  children: [
                    for (final s in device.slots)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: Icon(s.isPump ? Icons.water_drop_outlined : Icons.sensors),
                        title: Text('${l.slotLabel(s.slot + 1)} · ${s.isPump ? l.modulePump : l.moduleMoisture}'),
                        subtitle: Text([l.portLabel(s.port), if (s.isPump) l.pumpLimit(s.maxRunS)].join(' · ')),
                      ),
                  ],
                ),
        ),
        const SizedBox(height: Spacing.md),
        _Events(deviceId: device.id),
        const SizedBox(height: Spacing.md),
        Wrap(
          spacing: Spacing.sm,
          runSpacing: Spacing.sm,
          children: [
            actionButton(DeviceAction.identify, Icons.lightbulb_outline, l.identify, AppAction.identifyDevice),
            actionButton(DeviceAction.reboot, Icons.restart_alt, l.reboot, AppAction.manageDevices),
            if (canManage)
              OutlinedButton.icon(
                icon: const Icon(Icons.edit_outlined),
                label: Text(l.renameDevice),
                onPressed: () => _rename(context, ref),
              ),
            if (canManage)
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error),
                icon: const Icon(Icons.delete_outline),
                label: Text(l.removeDevice),
                onPressed: () => _remove(context, ref),
              ),
          ],
        ),
      ],
    );
  }

  Future<void> _send(BuildContext context, WidgetRef ref, DeviceAction action) async {
    try {
      await ref.read(actionsProvider).deviceAction(device.id, action);
      if (context.mounted) showSnackBar(context, context.l10n.deviceActionSent);
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }

  Future<void> _rename(BuildContext context, WidgetRef ref) async {
    final l = context.l10n;
    final controller = TextEditingController(text: device.name);
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l.renameDevice),
        content: TextField(controller: controller, autofocus: true, decoration: InputDecoration(labelText: l.deviceName)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text(l.cancel)),
          FilledButton(onPressed: () => Navigator.pop(context, controller.text.trim()), child: Text(l.save)),
        ],
      ),
    );
    controller.dispose();
    if (name == null || name.isEmpty) return;
    try {
      await ref.read(actionsProvider).renameDevice(device.id, name);
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }

  Future<void> _remove(BuildContext context, WidgetRef ref) async {
    final l = context.l10n;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l.removeDevice),
        content: Text(l.removeDeviceBody(device.name)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(l.cancel)),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(l.removeDevice)),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    try {
      final done = await withReauth(context, ref, () async {
        await ref.read(actionsProvider).deleteDevice(device.id, force: !device.reachable);
        return true;
      });
      if (done == true && context.mounted) context.go('/devices');
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}

class _Events extends ConsumerWidget {
  const _Events({required this.deviceId});

  final String deviceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final events = ref.watch(deviceEventsProvider(deviceId));
    return SectionCard(
      title: l.eventsTitle,
      child: AsyncBody(
        value: events,
        onRetry: () => ref.invalidate(deviceEventsProvider(deviceId)),
        data: (events) => events.isEmpty
            ? Text(l.noEvents)
            : Column(
                children: [
                  for (final e in events.take(10))
                    ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.history),
                      title: Text('${e['code']}'),
                      subtitle: Text(
                        e['ts'] == null ? '' : formatAgo(l, DateTime.parse(e['ts'] as String).toLocal()),
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}
