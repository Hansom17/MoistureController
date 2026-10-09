import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/format.dart';
import '../../core/app_data.dart';
import '../../core/permissions.dart';
import '../../data/models.dart';
import '../../ui/common.dart';
import '../../ui/app_scope.dart';

class AlertsScreen extends StatelessWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AppScope(
      builder: (context, user) => Consumer(
        builder: (context, ref, _) {
          final alerts = ref.watch(alertsProvider);
          return Scaffold(
            appBar: AppBar(title: Text(l.navAlerts)),
            body: RefreshIndicator(
              onRefresh: () => ref.refresh(alertsProvider.future),
              child: AsyncBody(
                value: alerts,
                onRetry: () => ref.invalidate(alertsProvider),
                data: (alerts) {
                  if (alerts.isEmpty) {
                    return ListView(
                      children: [
                        EmptyState(icon: Icons.eco_outlined, title: l.noAlerts),
                      ],
                    );
                  }
                  final open = alerts.where((a) => a.open).toList();
                  final closed = alerts.where((a) => !a.open).toList();
                  return ListView(
                    padding: const EdgeInsets.all(Spacing.lg),
                    children: [
                      if (open.isNotEmpty) ...[
                        _Header(l.openAlerts),
                        for (final a in open)
                          _AlertTile(role: user.role, alert: a),
                      ],
                      if (closed.isNotEmpty) ...[
                        _Header(l.closedAlerts),
                        for (final a in closed)
                          _AlertTile(role: user.role, alert: a),
                      ],
                    ],
                  );
                },
              ),
            ),
          );
        },
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(0, Spacing.md, 0, Spacing.sm),
    child: Text(text, style: Theme.of(context).textTheme.titleSmall),
  );
}

class _AlertTile extends ConsumerWidget {
  const _AlertTile({required this.role, required this.alert});

  final Role role;
  final Alert alert;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final status = StatusColors.of(context);
    final (icon, title, color) = switch (alert.kind) {
      AlertKind.deviceOffline => (
        Icons.wifi_off,
        l.alertDeviceOffline(alert.subject),
        status.error,
      ),
      AlertKind.batteryLow => (
        Icons.battery_alert,
        l.alertBatteryLow(alert.subject),
        status.warning,
      ),
      AlertKind.sensorSuspect => (
        Icons.sensors_off,
        l.alertSensorSuspect(alert.subject),
        status.warning,
      ),
      AlertKind.commandFailed => (
        Icons.water_drop_outlined,
        l.alertCommandFailed(alert.subject),
        status.error,
      ),
      AlertKind.safeMode => (
        Icons.shield_outlined,
        l.alertSafeMode(alert.subject),
        status.error,
      ),
      AlertKind.zigbeeOffline => (
        Icons.cell_tower,
        l.alertZigbeeOffline,
        status.error,
      ),
      AlertKind.other => (
        Icons.info_outline,
        l.alertOther(
          alert.subject,
          (alert.kindName ?? '').replaceAll('_', ' '),
        ),
        status.warning,
      ),
    };
    final subtitle = alert.open
        ? formatAgo(l, alert.createdAt)
        : l.acknowledgedAgo(
            formatAgo(l, alert.acknowledgedAt ?? alert.createdAt),
          );

    return Padding(
      padding: const EdgeInsets.only(bottom: Spacing.sm),
      child: Card(
        child: ListTile(
          leading: Icon(icon, color: alert.open ? color : null),
          title: Text(title),
          subtitle: Text(subtitle),
          trailing: alert.open
              ? RoleGate(
                  role: role,
                  action: AppAction.acknowledgeAlert,
                  builder: (context, allowed) => TextButton(
                    onPressed: allowed
                        ? () => ref
                              .read(actionsProvider)
                              .acknowledgeAlert(alert.id)
                              .catchError((Object e) {
                                if (context.mounted) {
                                  showErrorSnackBar(context, e);
                                }
                              })
                        : null,
                    child: Text(l.acknowledge),
                  ),
                )
              : null,
        ),
      ),
    );
  }
}
