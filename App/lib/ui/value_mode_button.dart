import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/format.dart';
import '../core/settings.dart';

/// App bar button that switches the moisture display between percent and the measured (raw) value.
class ValueModeButton extends ConsumerWidget {
  const ValueModeButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final measured = ref.watch(valueModeProvider) == ValueMode.measured;
    final l = context.l10n;
    return IconButton(
      tooltip: measured ? l.showPercent : l.showMeasured,
      icon: Icon(measured ? Icons.percent : Icons.sensors),
      onPressed: () => ref.read(valueModeProvider.notifier).toggle(),
    );
  }
}
