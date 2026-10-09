import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../core/permissions.dart';
import '../../core/session.dart';
import '../../data/models.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';
import '../../ui/status_chip.dart';
import '../../app/theme/app_colors.dart';

/// Gateway status: Zigbee2MQTT, the coordinator, versions, clock (App/specs.md Part A §4).
class GatewayScreen extends StatelessWidget {
  const GatewayScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AppScope(
      builder: (context, user) => Scaffold(
        appBar: AppBar(title: Text(l.gatewayTitle)),
        body: Consumer(
          builder: (context, ref, _) => AsyncBody(
            value: ref.watch(gatewayStatusProvider),
            onRetry: () => ref.invalidate(gatewayStatusProvider),
            data: (status) => _Details(role: user.role, status: status),
          ),
        ),
      ),
    );
  }
}

class _Details extends ConsumerWidget {
  const _Details({required this.role, required this.status});

  final Role role;
  final GatewayStatus status;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;

    StatusChip chip(bool ok, String good, String bad) => StatusChip(
      kind: ok ? StatusKind.ok : StatusKind.error,
      label: ok ? good : bad,
      icon: ok ? Icons.check_circle_outline : Icons.error_outline,
    );

    Widget row(String label, Widget value) =>
        ListTile(contentPadding: EdgeInsets.zero, dense: true, title: Text(label), trailing: value);

    return ListView(
      padding: const EdgeInsets.all(Spacing.lg),
      children: [
        SectionCard(
          title: l.gatewayServices,
          child: Column(
            children: [
              row(l.gatewayHub, chip(status.hubOnline, l.deviceOnline, l.deviceOffline)),
              row(
                l.gatewayZigbee,
                !status.hubOnline
                    ? const Text('—')
                    : chip(status.zigbee == 'online', l.deviceOnline, status.zigbee == 'offline' ? l.deviceOffline : l.statusUnknown),
              ),
              if (status.coordinator != null) row(l.gatewayCoordinator, Text(status.coordinator!)),
              if (status.hubVersion != null) row(l.gatewayHubVersion, Text(status.hubVersion!)),
              if (status.apiVersion != null) row(l.gatewayApiVersion, Text(status.apiVersion!)),
              if (status.clockSynced != null)
                row(l.gatewayClock, chip(status.clockSynced!, l.gatewayClockOk, l.gatewayClockBad)),
              if (status.dbSizeBytes != null)
                row(l.gatewayDatabase, Text('${(status.dbSizeBytes! / 1024 / 1024).toStringAsFixed(1)} MB')),
            ],
          ),
        ),
        if (can(role, AppAction.backup)) ...[
          const SizedBox(height: Spacing.md),
          FilledButton.tonalIcon(
            icon: const Icon(Icons.save_alt),
            label: Text(l.backupNow),
            onPressed: () async {
              try {
                await ref.read(repositoryProvider).backup();
                if (context.mounted) showSnackBar(context, l.backupDone);
              } catch (e) {
                if (context.mounted) showErrorSnackBar(context, e);
              }
            },
          ),
        ],
      ],
    );
  }
}
