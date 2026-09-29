import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import 'session.dart';

// Household-scoped data. Every provider is a family keyed by household id, so
// switching household never shows data of the previous one (App_Specs §3).

typedef PlantKey = ({String householdId, String plantId});
typedef ReadingsKey = ({String householdId, String plantId, ChartRange range});

final plantsProvider = FutureProvider.family<List<Plant>, String>(
  (ref, householdId) => ref.watch(repositoryProvider).plants(householdId),
);

final plantProvider = FutureProvider.family<Plant, PlantKey>((ref, key) async {
  final plants = await ref.watch(plantsProvider(key.householdId).future);
  return plants.firstWhere((p) => p.id == key.plantId);
});

final readingsProvider = FutureProvider.family<List<Reading>, ReadingsKey>(
  (ref, key) => ref
      .watch(repositoryProvider)
      .readings(key.householdId, key.plantId, key.range),
);

final commandsProvider = FutureProvider.family<List<Command>, PlantKey>(
  (ref, key) =>
      ref.watch(repositoryProvider).commands(key.householdId, key.plantId),
);

final rulesProvider = FutureProvider.family<List<Rule>, PlantKey>(
  (ref, key) =>
      ref.watch(repositoryProvider).rules(key.householdId, key.plantId),
);

final devicesProvider = FutureProvider.family<List<Device>, String>(
  (ref, householdId) => ref.watch(repositoryProvider).devices(householdId),
);

final alertsProvider = FutureProvider.family<List<Alert>, String>(
  (ref, householdId) => ref.watch(repositoryProvider).alerts(householdId),
);

/// Number of open alerts, for the navigation badge.
final openAlertCountProvider = Provider.family<int, String>((ref, householdId) {
  final alerts = ref.watch(alertsProvider(householdId)).value ?? const [];
  return alerts.where((a) => a.open).length;
});
