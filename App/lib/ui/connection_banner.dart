import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../app/router.dart';
import '../app/theme/app_colors.dart';
import '../app/theme/tokens.dart';
import '../core/api_endpoint.dart';
import '../core/format.dart';

/// Wraps the whole app: shows the API connection state above every screen
/// while the server is being searched for or unreachable (App/specs.md Part A §6.4.2).
class ConnectionScope extends ConsumerWidget {
  const ConnectionScope({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(apiEndpointProvider);
    final banner = switch (state) {
      ApiFixed() || ApiConnected() => null,
      _ => _ConnectionBanner(state: state),
    };
    if (banner == null) return child;
    return Column(
      children: [
        Material(
          color: StatusColors.of(
            context,
          ).warning.withValues(alpha: StatusColors.of(context).chipAlpha),
          child: SafeArea(bottom: false, child: banner),
        ),
        Expanded(
          child: MediaQuery.removePadding(
            context: context,
            removeTop: true,
            child: child,
          ),
        ),
      ],
    );
  }
}

class _ConnectionBanner extends ConsumerWidget {
  const _ConnectionBanner({required this.state});

  final ApiEndpointState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final colors = StatusColors.of(context);
    final controller = ref.read(apiEndpointProvider.notifier);
    void openServerScreen() => ref.read(routerProvider).go('/server');

    final (message, actions) = switch (state) {
      ApiChoose() => (
        l.connChoose,
        [TextButton(onPressed: openServerScreen, child: Text(l.serverTitle))],
      ),
      ApiUnreachable() => (
        l.connUnreachable,
        [
          TextButton(onPressed: controller.search, child: Text(l.retry)),
          TextButton(
            onPressed: openServerScreen,
            child: Text(l.connEnterAddress),
          ),
        ],
      ),
      _ => (l.connSearching, const <Widget>[]),
    };

    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: Spacing.lg,
        vertical: Spacing.sm,
      ),
      child: Row(
        children: [
          state is ApiSearching
              ? const SizedBox.square(
                  dimension: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Icon(Icons.wifi_off, color: colors.warning),
          const SizedBox(width: Spacing.md),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                color: colors.warning,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          ...actions,
        ],
      ),
    );
  }
}
