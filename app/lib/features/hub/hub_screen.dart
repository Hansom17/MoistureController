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

/// Household settings → Hub (App_Specs §4, §12).
class HubScreen extends StatelessWidget {
  const HubScreen({super.key, this.initialCode});

  /// Pre-filled from the deep link `/hub#u=<code>`.
  final String? initialCode;

  @override
  Widget build(BuildContext context) {
    return HouseholdScope(
      builder: (context, household) => Scaffold(
        appBar: AppBar(title: Text(context.l10n.hubTitle)),
        body: Consumer(
          builder: (context, ref, _) => AsyncBody(
            value: ref.watch(hubProvider(household.id)),
            onRetry: () => ref.invalidate(hubProvider(household.id)),
            data: (hub) => hub == null
                ? _NoHub(household: household, initialCode: initialCode)
                : _HubDetails(household: household, hub: hub),
          ),
        ),
      ),
    );
  }
}

// --- no hub yet: explain and claim ----------------------------------------------

class _NoHub extends StatelessWidget {
  const _NoHub({required this.household, this.initialCode});

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
                  Text(l.hubNoneTitle, style: theme.textTheme.titleLarge),
                  const SizedBox(height: Spacing.sm),
                  Text(l.hubNoneBody, style: theme.textTheme.bodyMedium),
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

  /// 8 Crockford base32 chars, dash and spaces optional (hub.md §3.1).
  static bool _valid(String code) => RegExp(
    r'^[0-9A-Za-z]{8}$',
  ).hasMatch(code.replaceAll(RegExp(r'[\s-]'), ''));

  Future<void> _submit() async {
    final l = context.l10n;
    if (!_valid(_code.text)) {
      setState(() => _error = l.hubCodeInvalid);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(householdActionsProvider)
          .claimHub(widget.household.id, _code.text);
      if (mounted) showSnackBar(context, l.hubAdded);
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
            labelText: l.hubCodeLabel,
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
        Text(l.hubClaimNote, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: Spacing.lg),
        FilledButton.icon(
          onPressed: _busy ? null : _submit,
          icon: _busy
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.add_link),
          label: Text(l.hubAdd),
        ),
      ],
    );
  }
}

// --- hub present -----------------------------------------------------------------

class _HubDetails extends ConsumerWidget {
  const _HubDetails({required this.household, required this.hub});

  final Household household;
  final HubInfo hub;

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
              _StatusCard(hub: hub),
              const SizedBox(height: Spacing.md),
              _LanCard(household: household, hub: hub, admin: admin),
              if (toRepair.isNotEmpty) ...[
                const SizedBox(height: Spacing.md),
                SectionCard(
                  title: l.hubRepairTitle,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l.hubRepairBody),
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
                    label: Text(l.hubRemove),
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
        title: Text(l.hubRemoveTitle),
        content: Text(l.hubRemoveBody),
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
            child: Text(l.hubRemove),
          ),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    try {
      await ref.read(householdActionsProvider).removeHub(household.id);
      if (context.mounted) showSnackBar(context, l.hubRemoved);
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.hub});

  final HubInfo hub;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodyMedium?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    );

    final StatusChip connection;
    if (hub.enrolling) {
      connection = StatusChip(kind: StatusKind.pending, label: l.hubEnrolling);
    } else if (hub.online) {
      connection = StatusChip(
        kind: StatusKind.ok,
        label: l.deviceOnline,
        icon: Icons.cloud_done_outlined,
      );
    } else {
      final since = hub.offlineSince;
      connection = StatusChip(
        kind: StatusKind.warning,
        icon: Icons.cloud_off_outlined,
        label: since == null
            ? l.deviceOffline
            : l.hubOfflineSince(formatTime(context, since)),
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
                    hub.id,
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
                if (!hub.enrolling)
                  hub.inSync
                      ? StatusChip(
                          kind: StatusKind.ok,
                          label: l.hubInSync,
                          icon: Icons.sync,
                        )
                      : StatusChip(
                          kind: StatusKind.pending,
                          label: l.hubSyncing,
                        ),
              ],
            ),
            if (hub.enrolling) ...[
              const SizedBox(height: Spacing.lg),
              const LinearProgressIndicator(),
            ] else ...[
              const SizedBox(height: Spacing.md),
              const Divider(height: 1),
              const SizedBox(height: Spacing.sm),
              row(
                l.hubAgentVersion,
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text([hub.agentVersion ?? '—', ?hub.arch].join(' · ')),
                    if (hub.updateAvailable)
                      Padding(
                        padding: const EdgeInsets.only(top: Spacing.xs),
                        child: StatusChip(
                          kind: StatusKind.pending,
                          icon: Icons.system_update_alt,
                          label: l.hubUpdateAvailable(hub.latestAgentVersion!),
                        ),
                      ),
                  ],
                ),
              ),
              if (hub.updateAvailable)
                Padding(
                  padding: const EdgeInsets.only(bottom: Spacing.xs),
                  child: SelectableText(
                    l.hubUpdateHint,
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
              row(
                l.hubClock,
                hub.timeSynced == false
                    ? StatusChip(kind: StatusKind.error, label: l.hubClockBad)
                    : Text(hub.timeSynced == true ? l.hubClockOk : '—'),
              ),
              row(l.hubQueue, Text('${hub.queueDepth ?? '—'}')),
              row(
                l.hubLastReport,
                Text(
                  hub.lastStateAt == null
                      ? '—'
                      : formatAgo(l, hub.lastStateAt!),
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
    required this.hub,
    required this.admin,
  });

  final Household household;
  final HubInfo hub;
  final bool admin;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final overridden = hub.lanHostOverride != null;
    return SectionCard(
      title: l.hubLanAddress,
      trailing: admin && !hub.enrolling
          ? TextButton(
              onPressed: () => _edit(context, ref),
              child: Text(l.edit),
            )
          : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            hub.lanHost ?? l.hubLanUnknown,
            style: theme.textTheme.titleLarge?.copyWith(
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(height: Spacing.xs),
          if (hub.lanHost != null)
            Text(
              overridden ? l.hubLanOverridden : l.hubLanReported,
              style: theme.textTheme.labelMedium,
            ),
          const SizedBox(height: Spacing.sm),
          Text(
            l.hubLanHint,
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
      text: hub.lanHostOverride ?? hub.lanHost,
    );
    // null = cancelled; '' = back to the reported address.
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l.hubLanAddress),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(hintText: '192.168.1.20'),
        ),
        actions: [
          if (hub.lanHostOverride != null)
            TextButton(
              onPressed: () => Navigator.pop(context, ''),
              child: Text(l.hubLanReset),
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
          .setHubLanHost(household.id, result.isEmpty ? null : result);
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
