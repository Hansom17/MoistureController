import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../data/models.dart';

/// App bar title that opens the household switcher (App_Specs §4).
class HouseholdSwitcherButton extends ConsumerWidget {
  const HouseholdSwitcherButton({super.key, required this.current});

  final Household current;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return TextButton.icon(
      style: TextButton.styleFrom(
        foregroundColor: Theme.of(context).colorScheme.onSurface,
        textStyle: Theme.of(context).textTheme.titleLarge,
      ),
      onPressed: () => _open(context, ref),
      icon: const Icon(Icons.expand_more),
      iconAlignment: IconAlignment.end,
      label: Text(current.name, overflow: TextOverflow.ellipsis),
    );
  }

  void _open(BuildContext context, WidgetRef ref) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => Consumer(
        builder: (context, ref, _) {
          final l = context.l10n;
          final households = ref.watch(householdsProvider).value ?? const [];
          return SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
                  child: Text(
                    l.switchHousehold,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                for (final h in households)
                  ListTile(
                    leading: Icon(
                      h.id == current.id
                          ? Icons.radio_button_checked
                          : Icons.radio_button_unchecked,
                    ),
                    title: Text(h.name),
                    trailing: Chip(label: Text(roleLabel(l, h.role))),
                    onTap: () {
                      ref
                          .read(selectedHouseholdIdProvider.notifier)
                          .select(h.id);
                      Navigator.pop(context);
                    },
                  ),
                const SizedBox(height: 8),
              ],
            ),
          );
        },
      ),
    );
  }
}
