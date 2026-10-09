import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/models.dart';
import '../data/repositories/moisture_repository.dart';

/// Overridden in `main_*.dart` with the flavor's repository.
final repositoryProvider = Provider<MoistureRepository>(
  (ref) => throw UnimplementedError('repositoryProvider must be overridden'),
);

/// Overridden in `main_*.dart` with the loaded instance.
final sharedPreferencesProvider = Provider<SharedPreferences>(
  (ref) =>
      throw UnimplementedError('sharedPreferencesProvider must be overridden'),
);

/// `GET /me/households` with the user's role in each.
final householdsProvider = FutureProvider<List<Household>>(
  (ref) => ref.watch(repositoryProvider).households(),
);

const _lastHouseholdKey = 'last_household_id';

/// The household the user last opened (persisted, UI preference only).
final selectedHouseholdIdProvider =
    NotifierProvider<SelectedHouseholdId, String?>(SelectedHouseholdId.new);

class SelectedHouseholdId extends Notifier<String?> {
  @override
  String? build() =>
      ref.watch(sharedPreferencesProvider).getString(_lastHouseholdKey);

  void select(String id) {
    state = id;
    ref.read(sharedPreferencesProvider).setString(_lastHouseholdKey, id);
  }
}

/// The current household; falls back to the first one when the stored id is
/// unknown. Errors with [NoHouseholdException] when the user has none.
final currentHouseholdProvider = FutureProvider<Household>((ref) async {
  final households = await ref.watch(householdsProvider.future);
  if (households.isEmpty) throw const NoHouseholdException();
  final id = ref.watch(selectedHouseholdIdProvider);
  return households.firstWhere(
    (h) => h.id == id,
    orElse: () => households.first,
  );
});

class NoHouseholdException implements Exception {
  const NoHouseholdException();
}
