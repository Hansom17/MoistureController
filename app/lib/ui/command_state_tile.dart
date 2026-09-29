import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';
import '../core/format.dart';
import '../data/models.dart';
import 'status_chip.dart';

/// One watering command with its live state (App_Specs §7).
class CommandStateTile extends StatelessWidget {
  const CommandStateTile({super.key, required this.command, this.onCancel});

  final Command command;

  /// Shown only for queued commands; null hides the cancel button.
  final VoidCallback? onCancel;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final c = command;
    final (kind, label) = switch (c.state) {
      CommandState.queued => (
        StatusKind.pending,
        l.commandQueued(formatTime(context, c.expectedAt)),
      ),
      CommandState.delivered => (StatusKind.pending, l.commandDelivered),
      CommandState.running => (
        StatusKind.pending,
        l.commandRunning(formatTime(context, c.runningUntil ?? c.expectedAt)),
      ),
      CommandState.done => (StatusKind.ok, l.commandDone),
      CommandState.failed => (StatusKind.error, l.commandFailed),
      CommandState.expired => (StatusKind.error, l.commandExpired),
      CommandState.cancelled => (StatusKind.sleeping, l.commandCancelled),
    };
    final origin = switch (c.origin) {
      CommandOrigin.user => l.originUser,
      CommandOrigin.cloudRule => l.originCloudRule,
      CommandOrigin.hubRule => l.originHubRule,
    };
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: c.state == CommandState.running
          ? const SizedBox.square(
              dimension: 24,
              child: CircularProgressIndicator(strokeWidth: 2.5),
            )
          : Icon(
              Icons.water_drop_outlined,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
      title: Text(l.commandTitle(c.seconds)),
      subtitle: Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Wrap(
          spacing: 8,
          runSpacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            StatusChip(kind: kind, label: label, detail: c.failureReason),
            Text('$origin · ${formatAgo(l, c.createdAt)}'),
          ],
        ),
      ),
      trailing: c.state == CommandState.queued && onCancel != null
          ? IconButton(
              tooltip: l.cancelCommand,
              icon: const Icon(Icons.close),
              onPressed: onCancel,
            )
          : null,
    );
  }
}
