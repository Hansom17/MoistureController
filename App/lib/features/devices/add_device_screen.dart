import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';
import '../../ui/reauth.dart';
import '../../ui/status_chip.dart';

/// Adding a device = opening the Zigbee join window (App/specs.md Part A §11).
class AddDeviceScreen extends StatelessWidget {
  const AddDeviceScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AppScope(
      builder: (context, user) => Scaffold(
        appBar: AppBar(title: Text(l.addDevice)),
        body: const _JoinBody(),
      ),
    );
  }
}

class _JoinBody extends ConsumerStatefulWidget {
  const _JoinBody();

  @override
  ConsumerState<_JoinBody> createState() => _JoinBodyState();
}

class _JoinBodyState extends ConsumerState<_JoinBody> {
  final _code = TextEditingController();
  Timer? _tick;
  var _busy = false;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    _code.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } catch (e) {
      if (mounted) showErrorSnackBar(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final join = ref.watch(joinStateProvider);
    final devices = ref.watch(devicesProvider).value ?? const <Device>[];

    return AsyncBody(
      value: join,
      onRetry: () => ref.invalidate(joinStateProvider),
      data: (join) {
        final left = join.endsAt?.difference(DateTime.now());
        final open = join.open && (left == null || !left.isNegative);
        final joined = [for (final id in join.deviceIds) devices.where((d) => d.id == id).firstOrNull]
            .whereType<Device>()
            .toList();
        return ListView(
          padding: const EdgeInsets.all(Spacing.lg),
          children: [
            SectionCard(
              title: open ? l.joinOpenTitle : l.joinIdleTitle,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(l.joinInstructions),
                  const SizedBox(height: Spacing.md),
                  if (open) ...[
                    Row(
                      children: [
                        const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2.5)),
                        const SizedBox(width: Spacing.md),
                        Expanded(
                          child: Text(l.joinCountdown(left == null ? '—' : _mmss(left)),
                              style: theme.textTheme.titleMedium),
                        ),
                        OutlinedButton(
                          onPressed: _busy ? null : () => _run(() => ref.read(actionsProvider).closeJoin()),
                          child: Text(l.joinClose),
                        ),
                      ],
                    ),
                  ] else ...[
                    TextField(
                      controller: _code,
                      decoration: InputDecoration(labelText: l.installCode, helperText: l.installCodeHint),
                    ),
                    const SizedBox(height: Spacing.md),
                    if (join.error != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: Spacing.sm),
                        child: Text(join.error!, style: TextStyle(color: theme.colorScheme.error)),
                      ),
                    FilledButton.icon(
                      icon: const Icon(Icons.wifi_tethering),
                      label: Text(l.joinOpen),
                      onPressed: _busy
                          ? null
                          : () => _run(() => ref.read(actionsProvider).openJoin(installCode: _code.text)),
                    ),
                  ],
                ],
              ),
            ),
            for (final d in joined) ...[
              const SizedBox(height: Spacing.md),
              _JoinedDevice(device: d),
            ],
            if (!open && joined.isEmpty && join.deviceIds.isEmpty && join.endsAt == null)
              const SizedBox.shrink(),
          ],
        );
      },
    );
  }

  String _mmss(Duration d) =>
      '${d.inMinutes}:${(d.inSeconds % 60).toString().padLeft(2, '0')}';
}

/// A device that joined during the window, with the steps it goes through.
class _JoinedDevice extends ConsumerStatefulWidget {
  const _JoinedDevice({required this.device});

  final Device device;

  @override
  ConsumerState<_JoinedDevice> createState() => _JoinedDeviceState();
}

class _JoinedDeviceState extends ConsumerState<_JoinedDevice> {
  late final _name = TextEditingController(text: widget.device.name);

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  /// joined → interviewing → configuring → ready
  int get _step => switch (widget.device.status) {
    DeviceStatus.joining => 1,
    DeviceStatus.ready => 2,
    DeviceStatus.joinFailed || DeviceStatus.unsupported => 1,
    _ => 3,
  };

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final d = widget.device;
    final failed = d.status == DeviceStatus.joinFailed;
    final unsupported = d.status == DeviceStatus.unsupported;
    final steps = [l.stepJoined, l.stepInterviewing, l.stepConfiguring, l.stepReady];
    final theme = Theme.of(context);

    return SectionCard(
      title: d.name,
      trailing: StatusChip.device(context, d),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (i, s) in steps.indexed)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: i < _step || (i == _step && d.status == DeviceStatus.online)
                  ? Icon(Icons.check_circle, color: theme.colorScheme.primary)
                  : i == _step && !failed && !unsupported
                  ? const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2.5))
                  : i == _step
                  ? Icon(Icons.error_outline, color: theme.colorScheme.error)
                  : const Icon(Icons.radio_button_unchecked),
              title: Text(s),
            ),
          if (failed) Text(l.joinFailedBody),
          if (unsupported) Text(l.joinUnsupportedBody(d.model ?? '?')),
          if (d.status == DeviceStatus.online) ...[
            const SizedBox(height: Spacing.sm),
            TextField(controller: _name, decoration: InputDecoration(labelText: l.deviceName)),
            const SizedBox(height: Spacing.md),
            Row(
              children: [
                FilledButton(
                  onPressed: () async {
                    final name = _name.text.trim();
                    final router = GoRouter.of(context);
                    try {
                      if (name.isNotEmpty && name != d.name) {
                        await ref.read(actionsProvider).renameDevice(d.id, name);
                      }
                      router.go('/devices/${d.id}/config');
                    } catch (e) {
                      if (context.mounted) showErrorSnackBar(context, e);
                    }
                  },
                  child: Text(l.joinConfigure),
                ),
              ],
            ),
          ],
          if (failed || unsupported)
            Padding(
              padding: const EdgeInsets.only(top: Spacing.md),
              child: OutlinedButton.icon(
                icon: const Icon(Icons.delete_outline),
                label: Text(l.joinRemoveRetry),
                onPressed: () async {
                  try {
                    await withReauth(context, ref, () => ref.read(actionsProvider).deleteDevice(d.id, force: true));
                  } catch (e) {
                    if (context.mounted) showErrorSnackBar(context, e);
                  }
                },
              ),
            ),
        ],
      ),
    );
  }
}
