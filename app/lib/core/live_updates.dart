import 'dart:async';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import 'household_data.dart';
import 'session.dart';

/// Keeps the live event stream of one household open while watched and
/// invalidates the matching providers on each event (App_Specs §6.2).
final liveUpdatesProvider = Provider.family<void, String>((ref, householdId) {
  final repository = ref.watch(repositoryProvider);
  StreamSubscription<LiveEvent>? subscription;
  Timer? retry;
  var attempt = 0;
  var disposed = false;

  void connect() {
    subscription = repository
        .events(householdId)
        .listen(
          (event) {
            attempt = 0;
            applyLiveEvent(ref, householdId, event);
          },
          onError: (Object _) {
            // Reconnect with exponential backoff 1 s → 30 s; then refresh
            // everything, as events may have been missed.
            subscription?.cancel();
            if (disposed) return;
            final delay = Duration(seconds: min(30, 1 << attempt++));
            retry = Timer(delay, () {
              if (disposed) return;
              applyLiveEvent(
                ref,
                householdId,
                const LiveEvent(LiveEventKind.resync),
              );
              connect();
            });
          },
        );
  }

  connect();
  ref.onDispose(() {
    disposed = true;
    retry?.cancel();
    subscription?.cancel();
  });
});

void applyLiveEvent(Ref ref, String householdId, LiveEvent event) {
  switch (event.kind) {
    case LiveEventKind.reading:
      ref.invalidate(plantsProvider(householdId));
      ref.invalidate(readingsProvider);
    case LiveEventKind.command:
      ref.invalidate(commandsProvider);
    case LiveEventKind.device:
    case LiveEventKind.config:
      ref.invalidate(devicesProvider(householdId));
    case LiveEventKind.alert:
      ref.invalidate(alertsProvider(householdId));
    case LiveEventKind.gateway:
      ref.invalidate(householdsProvider);
      ref.invalidate(gatewayProvider(householdId));
    case LiveEventKind.household:
      ref.invalidate(householdsProvider);
    case LiveEventKind.rule:
      ref.invalidate(rulesProvider);
    case LiveEventKind.resync:
      ref.invalidate(householdsProvider);
      ref.invalidate(plantsProvider(householdId));
      ref.invalidate(readingsProvider);
      ref.invalidate(commandsProvider);
      ref.invalidate(rulesProvider);
      ref.invalidate(devicesProvider(householdId));
      ref.invalidate(alertsProvider(householdId));
      ref.invalidate(gatewayProvider(householdId));
  }
}
