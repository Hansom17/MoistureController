import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../ui/common.dart';

/// Create or edit a watering rule: "below X % → water Y s, at most every Z h".
Future<void> showRuleEditor(
  BuildContext context,
  WidgetRef ref,
  Household household,
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
            minIntervalHours: 6,
            enabled: true,
          ),
      isNew: rule == null,
    ),
  );
  if (result == null) return;
  final actions = ref.read(householdActionsProvider);
  try {
    result.delete
        ? await actions.deleteRule(household.id, result.rule)
        : await actions.saveRule(household.id, result.rule);
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
  const _RuleDialog({
    required this.plant,
    required this.rule,
    required this.isNew,
  });

  final Plant plant;
  final Rule rule;
  final bool isNew;

  @override
  State<_RuleDialog> createState() => _RuleDialogState();
}

class _RuleDialogState extends State<_RuleDialog> {
  late var _rule = widget.rule;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
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
              onChanged: (v) =>
                  setState(() => _rule = _rule.copyWith(belowPercent: v)),
            ),
            _SliderField(
              label: l.ruleDuration,
              value: _rule.waterSeconds,
              min: 1,
              max: widget.plant.maxRunS,
              format: l.secondsValue,
              onChanged: (v) =>
                  setState(() => _rule = _rule.copyWith(waterSeconds: v)),
            ),
            _SliderField(
              label: l.ruleInterval,
              value: _rule.minIntervalHours,
              min: 1,
              max: 48,
              format: l.hoursValue,
              onChanged: (v) =>
                  setState(() => _rule = _rule.copyWith(minIntervalHours: v)),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l.ruleEnabled),
              value: _rule.enabled,
              onChanged: (v) =>
                  setState(() => _rule = _rule.copyWith(enabled: v)),
            ),
          ],
        ),
      ),
      actions: [
        if (!widget.isNew)
          TextButton(
            style: TextButton.styleFrom(
              foregroundColor: Theme.of(context).colorScheme.error,
            ),
            onPressed: () =>
                Navigator.pop(context, _RuleResult(_rule, delete: true)),
            child: Text(l.delete),
          ),
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text(l.cancel),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, _RuleResult(_rule)),
          child: Text(l.save),
        ),
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
