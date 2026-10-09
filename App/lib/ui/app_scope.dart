import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/app_data.dart';
import '../core/format.dart';
import '../core/live_updates.dart';
import '../core/session.dart';
import '../data/models.dart';
import 'common.dart';

/// Builds [builder] for the signed-in user and keeps the live event stream open while it is shown.
/// The router only shows these screens to signed-in users; the loading and error states cover the
/// moment around start-up (App/specs.md Part A §5).
class AppScope extends ConsumerWidget {
  const AppScope({super.key, required this.builder});

  final Widget Function(BuildContext context, AppUser user) builder;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    return session.when(
      skipLoadingOnReload: true,
      skipLoadingOnRefresh: true,
      data: (user) {
        if (user == null) return const Center(child: CircularProgressIndicator());
        ref.watch(liveUpdatesProvider);
        return builder(context, user);
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => ErrorState(error: e, onRetry: () => ref.invalidate(sessionProvider)),
    );
  }
}

/// Standard loading/error handling for an [AsyncValue] inside a screen.
class AsyncBody<T> extends StatelessWidget {
  const AsyncBody({
    super.key,
    required this.value,
    required this.data,
    required this.onRetry,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) data;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => value.when(
    skipLoadingOnReload: true,
    skipLoadingOnRefresh: true,
    data: data,
    loading: () => const Center(
      child: Padding(
        padding: EdgeInsets.all(24),
        child: CircularProgressIndicator(),
      ),
    ),
    error: (e, _) => ErrorState(error: e, onRetry: onRetry),
  );
}

/// Banner for trouble on the gateway box: the hub is away or Zigbee is down (App/specs.md Part A §7).
class GatewayBannerHost extends ConsumerWidget {
  const GatewayBannerHost({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final status = ref.watch(gatewayStatusProvider).value;
    if (status == null) return const SizedBox.shrink();
    final message = !status.hubOnline
        ? l.bannerHubDown
        : status.zigbeeDown
        ? l.bannerZigbeeDown
        : null;
    return message == null ? const SizedBox.shrink() : InfoBanner(message: message);
  }
}
