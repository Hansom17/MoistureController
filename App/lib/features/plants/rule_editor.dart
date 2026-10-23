import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../ui/common.dart';

/// Create or edit a watering rule: "below X % → water Y s, at most every Z h and N times a day".
Future<void> showRuleEditor(
  BuildContext context,
  WidgetRef ref,
  Plant plant, {
  Rule? rule,
}) async {
  final result = await showDialog<_RuleResult>(
    context: context,
    builder: (context) => _RuleDialog(
      plant: plant,
      rule:
          rule ??
          Rule(
            id: '',
            plantId: plant.id,
            belowPercent: 30,
            waterSeconds: plant.maxRunS < 10 ? plant.maxRunS : 10,
            cooldownS: 6 * 3600,
            maxPerDay: 2,
            enabled: true,
          ),
      isNew: rule == null,
    ),
  );
  if (result == null) return;
  final actions = ref.read(actionsProvider);
  try {
    result.delete ? await actions.deleteRule(result.rule) : await actions.saveRule(result.rule);
  } catch (e) {
    if (context.mounted) showErrorSnackBar(context, e);
  }
}

class _RuleResult {
  const _RuleResult(this.rule, {this.delete = false});

  final Rule rule;
  final bool delete;
}

class _RuleDialog extends StatefulWidget {
  const _RuleDialog({required this.plant, required this.rule, required this.isNew});

  final Plant plant;
  final Rule rule;
  final bool isNew;

  @override
  State<_RuleDialog> createState() => _RuleDialogState();
}

class _RuleDialogState extends State<_RuleDialog> {
  late var _rule = widget.rule;

  TimeOfDay? _parse(String? hm) {
    if (hm == null) return null;
    final p = hm.split(':');
    return TimeOfDay(hour: int.parse(p[0]), minute: int.parse(p[1]));
  }

  String _fmt(TimeOfDay t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

  Future<void> _pickQuiet({required bool from}) async {
    final current = _parse(from ? _rule.quietFrom : _rule.quietTo) ??
        TimeOfDay(hour: from ? 22 : 7, minute: 0);
    final picked = await showTimePicker(context: context, initialTime: current);
    if (picked == null) return;
    setState(() {
      final other = from ? (_rule.quietTo ?? '07:00') : (_rule.quietFrom ?? '22:00');
      _rule = from
          ? _rule.copyWith(quietFrom: _fmt(picked), quietTo: other)
          : _rule.copyWith(quietFrom: other, quietTo: _fmt(picked));
    });
  }

  void _toggle(List<String> list, String value, bool on, void Function(List<String>) apply) {
    final next = [...list]..remove(value);
    if (on) next.add(value);
    setState(() => apply(next));
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final quiet = _rule.quietFrom != null;
    return AlertDialog(
      title: Text(widget.isNew ? l.addRule : l.editRule),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _SliderField(
              label: l.ruleBelow,
              value: _rule.belowPercent,
              min: 5,
              max: 90,
              format: l.percentValue,
              onChanged: (v) => setState(() => _rule = _rule.copyWith(belowPercent: v)),
            ),
            _SliderField(
              label: l.ruleDuration,
              value: _rule.waterSeconds,
              min: 1,
              max: widget.plant.maxRunS,
              format: l.secondsValue,
              onChanged: (v) => setState(() => _rule = _rule.copyWith(waterSeconds: v)),
            ),
            _SliderField(
              label: l.ruleInterval,
              value: _rule.cooldownHours.clamp(1, 48),
              min: 1,
              max: 48,
              format: l.hoursValue,
              onChanged: (v) => setState(() => _rule = _rule.copyWith(cooldownS: v * 3600)),
            ),
            _SliderField(
              label: l.ruleMaxPerDay,
              value: _rule.maxPerDay,
              min: 1,
              max: 6,
              format: (v) => '$v',
              onChanged: (v) => setState(() => _rule = _rule.copyWith(maxPerDay: v)),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l.ruleQuietHours),
              value: quiet,
              onChanged: (v) => setState(
                () => _rule = v
                    ? _rule.copyWith(quietFrom: '22:00', quietTo: '07:00')
                    : _rule.copyWith(clearQuiet: true),
              ),
            ),
            if (quiet)
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => _pickQuiet(from: true),
                      child: Text(l.quietFrom(_rule.quietFrom!)),
                    ),
                  ),
                  const SizedBox(width: Spacing.md),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => _pickQuiet(from: false),
                      child: Text(l.quietTo(_rule.quietTo!)),
                    ),
                  ),
                ],
              ),
            const SizedBox(height: Spacing.md),
            Text(l.ruleNotify, style: Theme.of(context).textTheme.titleSmall),
            Wrap(
              spacing: Spacing.sm,
              children: [
                for (final (ch, label) in [('app', l.channelApp), ('telegram', l.channelTelegram)])
                  FilterChip(
                    label: Text(label),
                    selected: _rule.notifyChannels.contains(ch),
                    onSelected: (on) => _toggle(
                      _rule.notifyChannels, ch, on, (n) => _rule = _rule.copyWith(notifyChannels: n)),
                  ),
              ],
            ),
            Wrap(
              spacing: Spacing.sm,
              children: [
                for (final (ev, label) in [
                  ('watered', l.notifyWatered),
                  ('failed', l.notifyFailed),
                  ('skipped_problem', l.notifySkipped),
                ])
                  FilterChip(
                    label: Text(label),
                    selected: _rule.notifyOn.contains(ev),
                    onSelected: (on) =>
                        _toggle(_rule.notifyOn, ev, on, (n) => _rule = _rule.copyWith(notifyOn: n)),
                  ),
              ],
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l.ruleEnabled),
              value: _rule.enabled,
              onChanged: (v) => setState(() => _rule = _rule.copyWith(enabled: v)),
            ),
          ],
        ),
      ),
      actions: [
        if (!widget.isNew)
          TextButton(
            style: TextButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error),
            onPressed: () => Navigator.pop(context, _RuleResult(_rule, delete: true)),
            child: Text(l.delete),
          ),
        TextButton(onPressed: () => Navigator.pop(context), child: Text(l.cancel)),
        FilledButton(onPressed: () => Navigator.pop(context, _RuleResult(_rule)), child: Text(l.save)),
      ],
    );
  }
}

class _SliderField extends StatelessWidget {
  const _SliderField({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.format,
    required this.onChanged,
  });

  final String label;
  final int value;
  final int min;
  final int max;
  final String Function(int) format;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final v = value.clamp(min, max);
    return Padding(
      padding: const EdgeInsets.only(top: Spacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text(label)),
              Text(format(v), style: Theme.of(context).textTheme.titleSmall),
            ],
          ),
          Slider(
            value: v.toDouble(),
            min: min.toDouble(),
            max: max.toDouble(),
            divisions: max > min ? max - min : null,
            label: format(v),
            onChanged: (d) => onChanged(d.round()),
          ),
        ],
      ),
    );
  }
}
