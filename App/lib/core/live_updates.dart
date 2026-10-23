import 'dart:async';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import 'app_data.dart';
import 'session.dart';

/// Messages the gateway wants shown (rule notifications), e.g. as a snack bar in the shell.
final notificationBusProvider = Provider<StreamController<String>>((ref) {
  final controller = StreamController<String>.broadcast();
  ref.onDispose(controller.close);
  return controller;
});

final notificationsProvider = StreamProvider<String>(
  (ref) => ref.watch(notificationBusProvider).stream,
);

/// Keeps the live event stream open while watched and invalidates the matching providers on each
/// event (App/specs.md Part A §6.2).
final liveUpdatesProvider = Provider<void>((ref) {
  final repository = ref.watch(repositoryProvider);
  StreamSubscription<LiveEvent>? subscription;
  Timer? retry;
  var attempt = 0;
  var disposed = false;

  void connect() {
    subscription = repository.events().listen(
      (event) {
        attempt = 0;
        applyLiveEvent(ref, event);
      },
      onError: (Object _) {
        // Reconnect with exponential backoff 1 s → 30 s; then refresh
        // everything, as events may have been missed.
        subscription?.cancel();
        if (disposed) return;
        final delay = Duration(seconds: min(30, 1 << attempt++));
        retry = Timer(delay, () {
          if (disposed) return;
          applyLiveEvent(ref, const LiveEvent(LiveEventKind.resync));
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

void applyLiveEvent(Ref ref, LiveEvent event) {
  switch (event.kind) {
    case LiveEventKind.reading:
      ref.invalidate(plantsProvider);
      ref.invalidate(readingsProvider);
      ref.invalidate(devicesProvider);
    case LiveEventKind.plant:
      ref.invalidate(plantsProvider);
    case LiveEventKind.command:
      ref.invalidate(commandsProvider);
    case LiveEventKind.device:
    case LiveEventKind.config:
      ref.invalidate(devicesProvider);
      ref.invalidate(deviceConfigProvider);
      ref.invalidate(plantsProvider);
    case LiveEventKind.rule:
      ref.invalidate(rulesProvider);
      ref.invalidate(ruleExecutionsProvider);
    case LiveEventKind.alert:
      ref.invalidate(alertsProvider);
    case LiveEventKind.installation:
      ref.invalidate(installationProvider);
      ref.invalidate(metaProvider);
      ref.read(sessionProvider.notifier).refresh();
    case LiveEventKind.join:
      ref.invalidate(joinStateProvider);
      ref.invalidate(devicesProvider);
    case LiveEventKind.status:
      ref.invalidate(gatewayStatusProvider);
      ref.invalidate(metaProvider);
    case LiveEventKind.notification:
      if (event.text != null) ref.read(notificationBusProvider).add(event.text!);
    case LiveEventKind.resync:
      ref.invalidate(plantsProvider);
      ref.invalidate(readingsProvider);
      ref.invalidate(commandsProvider);
      ref.invalidate(rulesProvider);
      ref.invalidate(ruleExecutionsProvider);
      ref.invalidate(devicesProvider);
      ref.invalidate(deviceConfigProvider);
      ref.invalidate(joinStateProvider);
      ref.invalidate(alertsProvider);
      ref.invalidate(installationProvider);
      ref.invalidate(gatewayStatusProvider);
      ref.invalidate(metaProvider);
  }
}
