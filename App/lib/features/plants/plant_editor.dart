import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../ui/common.dart';

/// Create a plant, or change its name and where its sensor and pump are plugged in.
Future<Plant?> showPlantEditor(BuildContext context, WidgetRef ref, {Plant? plant}) async {
  final devices = (await ref.read(devicesProvider.future)).where((d) => !d.isNew).toList();
  if (!context.mounted) return null;
  final result = await showDialog<_PlantResult>(
    context: context,
    builder: (context) => _PlantDialog(plant: plant, devices: devices),
  );
  if (result == null || !context.mounted) return null;
  final actions = ref.read(actionsProvider);
  try {
    if (result.delete) {
      await actions.deletePlant(plant!.id);
      return null;
    }
    if (plant == null) {
      return await actions.createPlant(name: result.name, sensor: result.sensor, pump: result.pump);
    }
    await actions.updatePlant(plant.id, name: result.name, sensor: result.sensor, pump: result.pump);
  } catch (e) {
    if (context.mounted) showErrorSnackBar(context, e);
  }
  return null;
}

class _PlantResult {
  const _PlantResult(this.name, this.sensor, this.pump, {this.delete = false});

  final String name;
  final SlotRef sensor;
  final SlotRef pump;
  final bool delete;
}

class _PlantDialog extends StatefulWidget {
  const _PlantDialog({required this.plant, required this.devices});

  final Plant? plant;
  final List<Device> devices;

  @override
  State<_PlantDialog> createState() => _PlantDialogState();
}

class _PlantDialogState extends State<_PlantDialog> {
  late final _name = TextEditingController(text: widget.plant?.name ?? '');
  late SlotRef _sensor = widget.plant?.sensor ?? const SlotRef();
  late SlotRef _pump = widget.plant?.pump ?? const SlotRef();

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  /// Slots of the given module type, as dropdown entries "Device · slot 1 (P1)".
  List<DropdownMenuEntry<SlotRef>> _entries(String module) => [
    for (final d in widget.devices)
      for (final s in d.slots)
        if (s.module == module)
          DropdownMenuEntry(
            value: SlotRef(deviceId: d.id, slot: s.slot),
            label: '${d.name} · ${context.l10n.slotLabel(s.slot + 1)} (${s.port})',
          ),
  ];

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final sensors = _entries('moisture');
    final pumps = _entries('pump');
    SlotRef? initial(SlotRef r, List<DropdownMenuEntry<SlotRef>> entries) {
      for (final e in entries) {
        if (e.value.deviceId == r.deviceId && e.value.slot == r.slot) return e.value;
      }
      return null;
    }

    return AlertDialog(
      title: Text(widget.plant == null ? l.addPlant : l.editPlant),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _name,
              autofocus: widget.plant == null,
              decoration: InputDecoration(labelText: l.plantName),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: Spacing.lg),
            if (sensors.isEmpty && pumps.isEmpty)
              Text(l.plantNoSlots)
            else ...[
              DropdownMenu<SlotRef>(
                key: const ValueKey('sensor'),
                expandedInsets: EdgeInsets.zero,
                label: Text(l.plantSensor),
                initialSelection: initial(_sensor, sensors),
                dropdownMenuEntries: sensors,
                onSelected: (v) => _sensor = v ?? const SlotRef(),
              ),
              const SizedBox(height: Spacing.md),
              DropdownMenu<SlotRef>(
                key: const ValueKey('pump'),
                expandedInsets: EdgeInsets.zero,
                label: Text(l.plantPump),
                initialSelection: initial(_pump, pumps),
                dropdownMenuEntries: pumps,
                onSelected: (v) => _pump = v ?? const SlotRef(),
              ),
            ],
          ],
        ),
      ),
      actions: [
        if (widget.plant != null)
          TextButton(
            style: TextButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error),
            onPressed: () => Navigator.pop(context, _PlantResult(_name.text, _sensor, _pump, delete: true)),
            child: Text(l.delete),
          ),
        TextButton(onPressed: () => Navigator.pop(context), child: Text(l.cancel)),
        FilledButton(
          onPressed: _name.text.trim().isEmpty
              ? null
              : () => Navigator.pop(context, _PlantResult(_name.text.trim(), _sensor, _pump)),
          child: Text(l.save),
        ),
      ],
    );
  }
}
