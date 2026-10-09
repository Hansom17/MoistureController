import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';
import '../app/theme/tokens.dart';
import '../core/format.dart';
import '../data/models.dart';

/// Status shown as icon + label + colour, never colour alone
/// (App/specs.md Part B §2.4).
class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.kind,
    required this.label,
    this.detail,
    this.icon,
    this.tinted = true,
  });

  /// Chip for a device's connectivity and lifecycle state.
  factory StatusChip.device(
    BuildContext context,
    Device device, {
    bool withLastSeen = false,
  }) {
    final l = context.l10n;
    final (kind, label, icon) = switch (device.status) {
      DeviceStatus.online => (StatusKind.ok, l.deviceOnline, Icons.check_circle_outline),
      DeviceStatus.ready => (StatusKind.pending, l.deviceReady, Icons.hourglass_empty),
      DeviceStatus.joining => (StatusKind.pending, l.deviceJoining, Icons.sync),
      DeviceStatus.joinFailed => (StatusKind.error, l.deviceJoinFailed, Icons.error_outline),
      DeviceStatus.unsupported => (StatusKind.warning, l.deviceUnsupported, Icons.block),
      DeviceStatus.late => (StatusKind.warning, l.deviceLate, Icons.warning_amber_rounded),
      DeviceStatus.offline => (StatusKind.error, l.deviceOffline, Icons.error_outline),
      DeviceStatus.safeMode => (StatusKind.error, l.deviceSafeMode, Icons.shield_outlined),
    };
    final seen = device.lastSeen;
    final showSeen = withLastSeen && device.status != DeviceStatus.online && seen != null;
    return StatusChip(
      kind: kind,
      label: label,
      icon: icon,
      detail: showSeen ? l.lastSeen(formatAgo(l, seen)) : null,
    );
  }

  final StatusKind kind;
  final String label;
  final String? detail;
  final IconData? icon;

  /// False inside dialogs/sheets (`surfaceContainerHigh`), where the tint
  /// would push warning/error below 4.5 : 1.
  final bool tinted;

  static IconData defaultIcon(StatusKind kind) => switch (kind) {
    StatusKind.ok => Icons.check_circle_outline,
    StatusKind.sleeping => Icons.bedtime_outlined,
    StatusKind.pending => Icons.schedule,
    StatusKind.warning => Icons.warning_amber_rounded,
    StatusKind.error => Icons.error_outline,
  };

  @override
  Widget build(BuildContext context) {
    final colors = StatusColors.of(context);
    final color = colors.forKind(kind);
    final text = detail == null ? label : '$label · $detail';
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Spacing.sm,
        vertical: Spacing.xs,
      ),
      decoration: BoxDecoration(
        color: tinted ? color.withValues(alpha: colors.chipAlpha) : null,
        border: tinted ? null : Border.all(color: color.withValues(alpha: 0.5)),
        borderRadius: BorderRadius.circular(Radii.chip),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon ?? defaultIcon(kind), size: 16, color: color),
          const SizedBox(width: Spacing.xs),
          Flexible(
            child: Text(
              text,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(
                context,
              ).textTheme.labelMedium?.copyWith(color: color),
            ),
          ),
        ],
      ),
    );
  }
}
