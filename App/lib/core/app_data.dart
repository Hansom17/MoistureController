import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import 'session.dart';

// Gateway data. One installation, one set of providers; they live as long as the login
// (App/specs.md Part A §3).

final plantsProvider = FutureProvider<List<Plant>>(
  (ref) => ref.watch(repositoryProvider).plants(),
);

final plantProvider = FutureProvider.family<Plant, String>((ref, plantId) async {
  final plants = await ref.watch(plantsProvider.future);
  return plants.firstWhere((p) => p.id == plantId);
});

typedef ReadingsKey = ({String plantId, ChartRange range});

final readingsProvider = FutureProvider.family<List<Reading>, ReadingsKey>(
  (ref, key) => ref.watch(repositoryProvider).readings(key.plantId, key.range),
);

typedef BatteryKey = ({String deviceId, ChartRange range});

final batteryHistoryProvider = FutureProvider.family<List<BatteryPoint>, BatteryKey>(
  (ref, key) => ref.watch(repositoryProvider).batteryHistory(key.deviceId, key.range),
);

final commandsProvider = FutureProvider.family<List<Command>, String>(
  (ref, plantId) => ref.watch(repositoryProvider).commands(plantId),
);

final rulesProvider = FutureProvider.family<List<Rule>, String>(
  (ref, plantId) => ref.watch(repositoryProvider).rules(plantId),
);

typedef RuleKey = ({String plantId, String ruleId});

final ruleExecutionsProvider = FutureProvider.family<List<RuleExecution>, RuleKey>(
  (ref, key) => ref.watch(repositoryProvider).ruleExecutions(key.plantId, key.ruleId),
);

final devicesProvider = FutureProvider<List<Device>>(
  (ref) => ref.watch(repositoryProvider).devices(),
);

final deviceConfigProvider = FutureProvider.family<DeviceConfig, String>(
  (ref, deviceId) => ref.watch(repositoryProvider).deviceConfig(deviceId),
);

final boardProvider = FutureProvider.family<Board?, String>(
  (ref, name) => ref.watch(repositoryProvider).board(name),
);

final deviceEventsProvider = FutureProvider.family<List<Map<String, Object?>>, String>(
  (ref, deviceId) => ref.watch(repositoryProvider).deviceEvents(deviceId),
);

final joinStateProvider = FutureProvider<JoinState>(
  (ref) => ref.watch(repositoryProvider).joinState(),
);

final alertsProvider = FutureProvider<List<Alert>>(
  (ref) => ref.watch(repositoryProvider).alerts(),
);

/// Number of open (unacknowledged) alerts, for the navigation badge.
final openAlertCountProvider = Provider<int>((ref) {
  final alerts = ref.watch(alertsProvider).value ?? const [];
  return alerts.where((a) => a.open).length;
});

final installationProvider = FutureProvider<Installation>(
  (ref) => ref.watch(repositoryProvider).installation(),
);

final gatewayStatusProvider = FutureProvider<GatewayStatus>(
  (ref) => ref.watch(repositoryProvider).gatewayStatus(),
);

final usersProvider = FutureProvider<List<AppUser>>(
  (ref) => ref.watch(repositoryProvider).users(),
);

final invitesProvider = FutureProvider<List<Invite>>(
  (ref) => ref.watch(repositoryProvider).invites(),
);

final tokensProvider = FutureProvider<List<TokenInfo>>(
  (ref) => ref.watch(repositoryProvider).tokens(),
);

final auditProvider = FutureProvider<List<AuditEntry>>(
  (ref) => ref.watch(repositoryProvider).audit(),
);
