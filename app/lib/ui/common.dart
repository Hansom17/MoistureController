import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';
import '../app/theme/tokens.dart';
import '../core/format.dart';
import '../core/permissions.dart';
import '../data/models.dart';

/// Household-wide banner, e.g. "gateway offline since …" (App_Specs §7).
class HouseholdBanner extends StatelessWidget {
  const HouseholdBanner({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final colors = StatusColors.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: Spacing.lg,
        vertical: Spacing.md,
      ),
      color: colors.warning.withValues(alpha: colors.chipAlpha),
      child: Row(
        children: [
          Icon(Icons.cloud_off_outlined, color: colors.warning),
          const SizedBox(width: Spacing.md),
          Expanded(
            child: Text(message, style: TextStyle(color: colors.warning)),
          ),
        ],
      ),
    );
  }
}

/// Disables [child]'s action when the role doesn't allow it and explains why
/// in a tooltip (App_Specs §8). Use `builder` to receive the allowed flag.
class RoleGate extends StatelessWidget {
  const RoleGate({
    super.key,
    required this.role,
    required this.action,
    required this.builder,
  });

  final Role role;
  final AppAction action;
  final Widget Function(BuildContext context, bool allowed) builder;

  @override
  Widget build(BuildContext context) {
    final allowed = can(role, action);
    final child = builder(context, allowed);
    if (allowed) return child;
    return Tooltip(message: context.l10n.notAllowed, child: child);
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.body,
    this.action,
  });

  final IconData icon;
  final String title;
  final String? body;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(Spacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(height: Spacing.lg),
            Text(
              title,
              style: theme.textTheme.titleMedium,
              textAlign: TextAlign.center,
            ),
            if (body != null) ...[
              const SizedBox(height: Spacing.sm),
              Text(
                body!,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
            if (action != null) ...[
              const SizedBox(height: Spacing.lg),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}

class ErrorState extends StatelessWidget {
  const ErrorState({super.key, required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return EmptyState(
      icon: Icons.error_outline,
      title: describeError(l, error),
      action: OutlinedButton(onPressed: onRetry, child: Text(l.retry)),
    );
  }
}

/// Titled card section used on detail screens.
class SectionCard extends StatelessWidget {
  const SectionCard({
    super.key,
    required this.title,
    required this.child,
    this.trailing,
  });

  final String title;
  final Widget child;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Spacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                ?trailing,
              ],
            ),
            const SizedBox(height: Spacing.md),
            child,
          ],
        ),
      ),
    );
  }
}

void showErrorSnackBar(BuildContext context, Object error) {
  ScaffoldMessenger.of(
    context,
  ).showSnackBar(SnackBar(content: Text(describeError(context.l10n, error))));
}

void showSnackBar(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}
