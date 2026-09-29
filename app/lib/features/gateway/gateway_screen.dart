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

/// Household settings → Gateway (App_Specs §4, §12).
class GatewayScreen extends StatelessWidget {
  const GatewayScreen({super.key, this.initialCode});

  /// Pre-filled from the deep link `/gateway#u=<code>` (the gateway prints it as a QR code).
  final String? initialCode;

  @override
  Widget build(BuildContext context) {
    return HouseholdScope(
      builder: (context, household) => Scaffold(
        appBar: AppBar(title: Text(context.l10n.gatewayTitle)),
        body: Consumer(
          builder: (context, ref, _) => AsyncBody(
            value: ref.watch(gatewayProvider(household.id)),
            onRetry: () => ref.invalidate(gatewayProvider(household.id)),
            data: (gateway) => gateway == null
                ? _NoGateway(household: household, initialCode: initialCode)
                : _GatewayDetails(household: household, gateway: gateway),
          ),
        ),
      ),
    );
  }
}

// --- no gateway yet: explain and claim ----------------------------------------------

class _NoGateway extends StatelessWidget {
  const _NoGateway({required this.household, this.initialCode});

  final Household household;
  final String? initialCode;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(Spacing.lg),
      children: [
        _Constrained(
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(Spacing.xl),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.router_outlined,
                    size: 40,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(height: Spacing.md),
                  Text(l.gatewayNoneTitle, style: theme.textTheme.titleLarge),
                  const SizedBox(height: Spacing.sm),
                  Text(l.gatewayNoneBody, style: theme.textTheme.bodyMedium),
                  const SizedBox(height: Spacing.xl),
                  if (can(household.role, AppAction.manageDevices))
                    _ClaimForm(household: household, initialCode: initialCode)
                  else
                    Text(
                      l.notAllowed,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _ClaimForm extends ConsumerStatefulWidget {
  const _ClaimForm({required this.household, this.initialCode});

  final Household household;
  final String? initialCode;

  @override
  ConsumerState<_ClaimForm> createState() => _ClaimFormState();
}

class _ClaimFormState extends ConsumerState<_ClaimForm> {
  late final _code = TextEditingController(text: widget.initialCode ?? '');
  String? _error;
  var _busy = false;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  /// 8 Crockford base32 chars, dash and spaces optional (gateway_api.md §3.1).
  static bool _valid(String code) => RegExp(
    r'^[0-9A-Za-z]{8}$',
  ).hasMatch(code.replaceAll(RegExp(r'[\s-]'), ''));

  Future<void> _submit() async {
    final l = context.l10n;
    if (!_valid(_code.text)) {
      setState(() => _error = l.gatewayCodeInvalid);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(householdActionsProvider)
          .claimGateway(widget.household.id, _code.text);
      if (mounted) showSnackBar(context, l.gatewayAdded);
    } catch (e) {
      if (mounted) setState(() => _error = describeError(l, e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _code,
          autofocus: widget.initialCode == null,
          textCapitalization: TextCapitalization.characters,
          autocorrect: false,
          enableSuggestions: false,
          style: const TextStyle(
            fontSize: 20,
            letterSpacing: 2,
            fontFeatures: [FontFeature.tabularFigures()],
          ),
          decoration: InputDecoration(
            labelText: l.gatewayCodeLabel,
            hintText: 'K7QM-2XPA',
            errorText: _error,
            errorMaxLines: 3,
          ),
          onChanged: (_) {
            if (_error != null) setState(() => _error = null);
          },
          onSubmitted: (_) => _submit(),
        ),
        const SizedBox(height: Spacing.md),
        Text(l.gatewayClaimNote, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: Spacing.lg),
        FilledButton.icon(
          onPressed: _busy ? null : _submit,
          icon: _busy
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.add_link),
          label: Text(l.gatewayAdd),
        ),
      ],
    );
  }
}

// --- gateway present -----------------------------------------------------------------

class _GatewayDetails extends ConsumerWidget {
  const _GatewayDetails({required this.household, required this.gateway});

  final Household household;
  final GatewayInfo gateway;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final admin = can(household.role, AppAction.manageDevices);
    final devices = ref.watch(devicesProvider(household.id)).value ?? const [];
    final toRepair = devices.where((d) => d.needsRepair).toList();

    return ListView(
      padding: const EdgeInsets.all(Spacing.lg),
      children: [
        _Constrained(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _StatusCard(gateway: gateway),
              const SizedBox(height: Spacing.md),
              _LanCard(household: household, gateway: gateway, admin: admin),
              if (toRepair.isNotEmpty) ...[
                const SizedBox(height: Spacing.md),
                SectionCard(
                  title: l.gatewayRepairTitle,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l.gatewayRepairBody),
                      const SizedBox(height: Spacing.sm),
                      for (final d in toRepair)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const Icon(Icons.link_off),
                          title: Text(d.name),
                          trailing: StatusChip(
                            kind: StatusKind.warning,
                            label: l.deviceNeedsRepair,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
              if (admin) ...[
                const SizedBox(height: Spacing.xl),
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.error,
                    ),
                    icon: const Icon(Icons.delete_outline),
                    label: Text(l.gatewayRemove),
                    onPressed: () => _remove(context, ref),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Future<void> _remove(BuildContext context, WidgetRef ref) async {
    final l = context.l10n;
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        icon: const Icon(Icons.warning_amber_rounded),
        title: Text(l.gatewayRemoveTitle),
        content: Text(l.gatewayRemoveBody),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(l.cancel),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
              foregroundColor: Theme.of(context).colorScheme.onError,
            ),
            onPressed: () => Navigator.pop(context, true),
            child: Text(l.gatewayRemove),
          ),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    try {
      await ref.read(householdActionsProvider).removeGateway(household.id);
      if (context.mounted) showSnackBar(context, l.gatewayRemoved);
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.gateway});

  final GatewayInfo gateway;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodyMedium?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    );

    final StatusChip connection;
    if (gateway.enrolling) {
      connection = StatusChip(
        kind: StatusKind.pending,
        label: l.gatewayEnrolling,
      );
    } else if (gateway.online) {
      connection = StatusChip(
        kind: StatusKind.ok,
        label: l.deviceOnline,
        icon: Icons.cloud_done_outlined,
      );
    } else {
      final since = gateway.offlineSince;
      connection = StatusChip(
        kind: StatusKind.warning,
        icon: Icons.cloud_off_outlined,
        label: since == null
            ? l.deviceOffline
            : l.gatewayOfflineSince(formatTime(context, since)),
      );
    }

    Widget row(String label, Widget value) => Padding(
      padding: const EdgeInsets.symmetric(vertical: Spacing.xs + 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: Text(label, style: muted)),
          const SizedBox(width: Spacing.md),
          Flexible(
            child: Align(alignment: Alignment.centerRight, child: value),
          ),
        ],
      ),
    );

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Spacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(Icons.router_outlined, color: theme.colorScheme.primary),
                const SizedBox(width: Spacing.md),
                Expanded(
                  child: Text(
                    gateway.id,
                    style: theme.textTheme.titleMedium,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: Spacing.md),
            Wrap(
              spacing: Spacing.sm,
              runSpacing: Spacing.xs,
              children: [
                connection,
                if (!gateway.enrolling)
                  gateway.inSync
                      ? StatusChip(
                          kind: StatusKind.ok,
                          label: l.gatewayInSync,
                          icon: Icons.sync,
                        )
                      : StatusChip(
                          kind: StatusKind.pending,
                          label: l.gatewaySyncing,
                        ),
              ],
            ),
            if (gateway.enrolling) ...[
              const SizedBox(height: Spacing.lg),
              const LinearProgressIndicator(),
            ] else ...[
              const SizedBox(height: Spacing.md),
              const Divider(height: 1),
              const SizedBox(height: Spacing.sm),
              row(
                l.gatewayVersion,
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text([gateway.version ?? '—', ?gateway.arch].join(' · ')),
                    if (gateway.updateAvailable)
                      Padding(
                        padding: const EdgeInsets.only(top: Spacing.xs),
                        child: StatusChip(
                          kind: StatusKind.pending,
                          icon: Icons.system_update_alt,
                          label: l.gatewayUpdateAvailable(
                            gateway.latestVersion!,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              if (gateway.updateAvailable)
                Padding(
                  padding: const EdgeInsets.only(bottom: Spacing.xs),
                  child: SelectableText(
                    l.gatewayUpdateHint,
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
              row(
                l.gatewayClock,
                gateway.timeSynced == false
                    ? StatusChip(
                        kind: StatusKind.error,
                        label: l.gatewayClockBad,
                      )
                    : Text(gateway.timeSynced == true ? l.gatewayClockOk : '—'),
              ),
              if (gateway.adapters.isNotEmpty)
                row(l.gatewayAdapters, Text(gateway.adapters.join(', '))),
              row(l.gatewayOutbox, Text('${gateway.outboxDepth ?? '—'}')),
              row(
                l.gatewayLastReport,
                Text(
                  gateway.lastStateAt == null
                      ? '—'
                      : formatAgo(l, gateway.lastStateAt!),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _LanCard extends ConsumerWidget {
  const _LanCard({
    required this.household,
    required this.gateway,
    required this.admin,
  });

  final Household household;
  final GatewayInfo gateway;
  final bool admin;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final overridden = gateway.lanHostOverride != null;
    return SectionCard(
      title: l.gatewayLanAddress,
      trailing: admin && !gateway.enrolling
          ? TextButton(
              onPressed: () => _edit(context, ref),
              child: Text(l.edit),
            )
          : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            gateway.lanHost == null
                ? l.gatewayLanUnknown
                : '${gateway.lanHost}:${gateway.lanPort}',
            style: theme.textTheme.titleLarge?.copyWith(
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(height: Spacing.xs),
          if (gateway.lanHost != null)
            Text(
              overridden ? l.gatewayLanOverridden : l.gatewayLanReported,
              style: theme.textTheme.labelMedium,
            ),
          const SizedBox(height: Spacing.sm),
          Text(
            l.gatewayLanHint,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _edit(BuildContext context, WidgetRef ref) async {
    final l = context.l10n;
    final controller = TextEditingController(
      text: gateway.lanHostOverride ?? gateway.lanHost,
    );
    // null = cancelled; '' = back to the reported address.
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l.gatewayLanAddress),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(hintText: '192.168.1.20'),
        ),
        actions: [
          if (gateway.lanHostOverride != null)
            TextButton(
              onPressed: () => Navigator.pop(context, ''),
              child: Text(l.gatewayLanReset),
            ),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(l.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: Text(l.save),
          ),
        ],
      ),
    );
    controller.dispose();
    if (result == null || !context.mounted) return;
    try {
      await ref
          .read(householdActionsProvider)
          .setGatewayLanHost(household.id, result.isEmpty ? null : result);
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}

/// Keeps forms readable on wide screens.
class _Constrained extends StatelessWidget {
  const _Constrained({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.topCenter,
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 640),
      child: child,
    ),
  );
}
