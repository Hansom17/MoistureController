import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/format.dart';
import '../core/live_updates.dart';
import '../core/session.dart';
import '../data/models.dart';
import 'common.dart';

/// Resolves the current household, keeps its live stream open and builds
/// [builder] with it. Handles loading, error and "no household" states.
class HouseholdScope extends ConsumerWidget {
  const HouseholdScope({super.key, required this.builder});

  final Widget Function(BuildContext context, Household household) builder;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final household = ref.watch(currentHouseholdProvider);
    return household.when(
      skipLoadingOnReload: true,
      skipLoadingOnRefresh: true,
      data: (h) {
        ref.watch(liveUpdatesProvider(h.id));
        return builder(context, h);
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => e is NoHouseholdException
          ? EmptyState(
              icon: Icons.home_outlined,
              title: context.l10n.noHouseholdTitle,
              body: context.l10n.noHouseholdBody,
            )
          : ErrorState(
              error: e,
              onRetry: () => ref.invalidate(householdsProvider),
            ),
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
