import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../data/api_problem.dart';
import '../../data/models.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';

/// Slot editor (App/specs.md Part A §10): modules and ports of a device and its report intervals.
class ConfigEditorScreen extends StatelessWidget {
  const ConfigEditorScreen({super.key, required this.deviceId});

  final String deviceId;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AppScope(
      builder: (context, user) => Consumer(
        builder: (context, ref, _) {
          final config = ref.watch(deviceConfigProvider(deviceId));
          return Scaffold(
            appBar: AppBar(title: Text(l.editConfig)),
            body: AsyncBody(
              value: config,
              onRetry: () => ref.invalidate(deviceConfigProvider(deviceId)),
              data: (config) => _Loaded(deviceId: deviceId, config: config),
            ),
          );
        },
      ),
    );
  }
}

class _Loaded extends ConsumerWidget {
  const _Loaded({required this.deviceId, required this.config});

  final String deviceId;
  final DeviceConfig config;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final boardName = config.board;
    if (boardName == null) return EmptyState(icon: Icons.memory, title: context.l10n.configNoBoard);
    return AsyncBody(
      value: ref.watch(boardProvider(boardName)),
      onRetry: () => ref.invalidate(boardProvider(boardName)),
      data: (board) => board == null
          ? EmptyState(icon: Icons.memory, title: context.l10n.configNoBoard)
          : _Editor(deviceId: deviceId, config: config, board: board),
    );
  }
}

class _Editor extends ConsumerStatefulWidget {
  const _Editor({required this.deviceId, required this.config, required this.board});

  final String deviceId;
  final DeviceConfig config;
  final Board board;

  @override
  ConsumerState<_Editor> createState() => _EditorState();
}

class _EditorState extends ConsumerState<_Editor> {
  late DeviceConfigBody _body = widget.config.desired ?? widget.config.reported ?? const DeviceConfigBody();
  String? _error;
  var _saving = false;

  SlotConfig? _slot(int i) => _body.slots.where((s) => s.slot == i).firstOrNull;

  void _setSlot(int i, SlotConfig? s) {
    final others = _body.slots.where((x) => x.slot != i).toList();
    if (s != null) others.add(s);
    others.sort((a, b) => a.slot.compareTo(b.slot));
    setState(() => _body = _body.copyWith(slots: others));
  }

  /// Ports that support [module] and are not used by another slot.
  List<String> _freePorts(String module, int slot) {
    final used = {for (final s in _body.slots) if (s.slot != slot) s.port};
    return [
      for (final p in widget.board.ports)
        if (p.roles.contains(module) && !used.contains(p.id)) p.id,
    ];
  }

  Future<void> _save() async {
    final l = context.l10n;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await ref.read(actionsProvider).saveDeviceConfig(widget.deviceId, widget.config.desiredRev, _body);
      if (!mounted) return;
      showSnackBar(context, l.configSaved);
      context.pop();
    } on ApiProblem catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      if (e.type == ApiProblem.conflict) {
        ref.invalidate(deviceConfigProvider(widget.deviceId));
        setState(() => _error = l.configConflict);
      } else {
        setState(() => _error = describeError(l, e));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final rejected = widget.config.sync == ConfigSync.rejected;
    return ListView(
      padding: const EdgeInsets.all(Spacing.lg),
      children: [
        if (widget.config.sync != ConfigSync.inSync)
          Card(
            color: rejected ? theme.colorScheme.errorContainer : theme.colorScheme.secondaryContainer,
            child: Padding(
              padding: const EdgeInsets.all(Spacing.md),
              child: Row(
                children: [
                  Expanded(
                    child: Text(rejected
                        ? l.configRejectedBody(widget.config.error ?? '')
                        : l.configPendingBody(widget.config.desiredRev)),
                  ),
                  if (rejected && widget.config.reported != null)
                    TextButton(
                      onPressed: () => setState(() => _body = widget.config.reported!),
                      child: Text(l.configRevert),
                    ),
                ],
              ),
            ),
          ),
        SectionCard(
          title: l.reportIntervals,
          child: Column(
            children: [
              _IntField(
                label: l.reportInterval,
                value: _body.reportIntervalS,
                min: 10,
                max: 3600,
                suffix: 's',
                onChanged: (v) => setState(() => _body = _body.copyWith(reportIntervalS: v)),
              ),
              _IntField(
                label: l.fastReportInterval,
                value: _body.fastReportIntervalS,
                min: 10,
                max: 300,
                suffix: 's',
                onChanged: (v) => setState(() => _body = _body.copyWith(fastReportIntervalS: v)),
              ),
              _IntField(
                label: l.fastReportHold,
                value: _body.fastReportHoldS,
                min: 0,
                max: 1800,
                suffix: 's',
                onChanged: (v) => setState(() => _body = _body.copyWith(fastReportHoldS: v)),
              ),
            ],
          ),
        ),
        for (var i = 0; i < 6; i++) ...[
          const SizedBox(height: Spacing.md),
          _SlotCard(
            index: i,
            slot: _slot(i),
            freePorts: (m) => _freePorts(m, i),
            onChanged: (s) => _setSlot(i, s),
          ),
        ],
        const SizedBox(height: Spacing.lg),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: Spacing.md),
            child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
          ),
        FilledButton.icon(
          icon: const Icon(Icons.save_outlined),
          label: Text(l.save),
          onPressed: _saving ? null : _save,
        ),
        const SizedBox(height: Spacing.sm),
        Text(l.configApplyNote, style: theme.textTheme.bodySmall),
      ],
    );
  }
}

class _SlotCard extends StatelessWidget {
  const _SlotCard({required this.index, required this.slot, required this.freePorts, required this.onChanged});

  final int index;
  final SlotConfig? slot;
  final List<String> Function(String module) freePorts;
  final ValueChanged<SlotConfig?> onChanged;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final s = slot;
    final module = s?.module ?? 'empty';

    void pickModule(String? m) {
      if (m == null || m == 'empty') return onChanged(null);
      final ports = freePorts(m);
      if (ports.isEmpty) return;
      onChanged(SlotConfig(slot: index, module: m, port: ports.first));
    }

    return SectionCard(
      title: l.slotLabel(index + 1),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  key: ValueKey('module-$index-$module'),
                  initialValue: module,
                  decoration: InputDecoration(labelText: l.slotModule),
                  items: [
                    DropdownMenuItem(value: 'empty', child: Text(l.moduleEmpty)),
                    DropdownMenuItem(value: 'moisture', child: Text(l.moduleMoisture)),
                    DropdownMenuItem(value: 'pump', child: Text(l.modulePump)),
                  ],
                  onChanged: pickModule,
                ),
              ),
              if (s != null) ...[
                const SizedBox(width: Spacing.md),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: ValueKey('port-$index-${s.port}-${s.module}'),
                    initialValue: s.port,
                    decoration: InputDecoration(labelText: l.slotPort),
                    items: [
                      for (final p in {s.port, ...freePorts(s.module)}.toList()..sort())
                        DropdownMenuItem(value: p, child: Text(p)),
                    ],
                    onChanged: (p) => p == null ? null : onChanged(s.copyWith(port: p)),
                  ),
                ),
              ],
            ],
          ),
          if (s != null && s.isPump) ...[
            _IntField(label: l.pumpMaxRun, value: s.maxRunS, min: 1, max: 300, suffix: 's',
                onChanged: (v) => onChanged(s.copyWith(maxRunS: v))),
            _IntField(label: l.pumpMinPause, value: s.minPauseS, min: 0, max: 65535, suffix: 's',
                onChanged: (v) => onChanged(s.copyWith(minPauseS: v))),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l.pumpActiveHigh),
              value: s.activeHigh,
              onChanged: (v) => onChanged(s.copyWith(activeHigh: v)),
            ),
          ],
          if (s != null && !s.isPump) ...[
            _IntField(label: l.calDry, value: s.calDry, min: 0, max: 4095, onChanged: (v) => onChanged(s.copyWith(calDry: v))),
            _IntField(label: l.calWet, value: s.calWet, min: 0, max: 4095, onChanged: (v) => onChanged(s.copyWith(calWet: v))),
          ],
        ],
      ),
    );
  }
}

/// A number field that keeps the typed text and only reports valid values.
class _IntField extends StatefulWidget {
  const _IntField({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
    this.suffix,
  });

  final String label;
  final int value;
  final int min;
  final int max;
  final String? suffix;
  final ValueChanged<int> onChanged;

  @override
  State<_IntField> createState() => _IntFieldState();
}

class _IntFieldState extends State<_IntField> {
  late final _controller = TextEditingController(text: '${widget.value}');

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final parsed = int.tryParse(_controller.text);
    final valid = parsed != null && parsed >= widget.min && parsed <= widget.max;
    return Padding(
      padding: const EdgeInsets.only(top: Spacing.md),
      child: TextField(
        controller: _controller,
        keyboardType: TextInputType.number,
        decoration: InputDecoration(
          labelText: widget.label,
          suffixText: widget.suffix,
          helperText: '${widget.min}–${widget.max}',
          errorText: valid ? null : context.l10n.outOfRange,
        ),
        onChanged: (t) {
          final v = int.tryParse(t);
          setState(() {});
          if (v != null && v >= widget.min && v <= widget.max) widget.onChanged(v);
        },
      ),
    );
  }
}
