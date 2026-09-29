import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import 'household_data.dart';
import 'session.dart';

/// Write operations. Screens call these instead of the repository; each one
/// refreshes the affected providers (live events refresh them again later).
final householdActionsProvider = Provider<HouseholdActions>(
  HouseholdActions.new,
);

class HouseholdActions {
  HouseholdActions(this._ref);

  final Ref _ref;

  Future<Command> waterNow(
    String householdId,
    String plantId,
    int seconds,
  ) async {
    final command = await _ref
        .read(repositoryProvider)
        .waterNow(householdId, plantId, seconds);
    _ref.invalidate(
      commandsProvider((householdId: householdId, plantId: plantId)),
    );
    return command;
  }

  Future<void> cancelCommand(String householdId, Command command) async {
    await _ref.read(repositoryProvider).cancelCommand(householdId, command.id);
    _ref.invalidate(
      commandsProvider((householdId: householdId, plantId: command.plantId)),
    );
  }

  Future<void> saveRule(String householdId, Rule rule) async {
    await _ref.read(repositoryProvider).saveRule(householdId, rule);
    _ref.invalidate(
      rulesProvider((householdId: householdId, plantId: rule.plantId)),
    );
  }

  Future<void> deleteRule(String householdId, Rule rule) async {
    await _ref.read(repositoryProvider).deleteRule(householdId, rule);
    _ref.invalidate(
      rulesProvider((householdId: householdId, plantId: rule.plantId)),
    );
  }

  Future<void> deviceAction(
    String householdId,
    String deviceId,
    DeviceAction action,
  ) =>
      _ref.read(repositoryProvider).deviceAction(householdId, deviceId, action);

  Future<void> acknowledgeAlert(String householdId, String alertId) async {
    await _ref.read(repositoryProvider).acknowledgeAlert(householdId, alertId);
    _ref.invalidate(alertsProvider(householdId));
  }

  // --- hub (App_Specs §12) ----------------------------------------------------------

  Future<HubInfo> claimHub(String householdId, String userCode) async {
    final hub = await _ref
        .read(repositoryProvider)
        .claimHub(householdId, userCode);
    _hubChanged(householdId);
    return hub;
  }

  Future<void> setHubLanHost(
    String householdId,
    String? lanHostOverride,
  ) async {
    await _ref
        .read(repositoryProvider)
        .setHubLanHost(householdId, lanHostOverride);
    _ref.invalidate(hubProvider(householdId));
  }

  Future<void> removeHub(String householdId) async {
    await _ref.read(repositoryProvider).removeHub(householdId);
    _hubChanged(householdId);
  }

  void _hubChanged(String householdId) {
    _ref.invalidate(hubProvider(householdId));
    _ref.invalidate(householdsProvider);
    _ref.invalidate(devicesProvider(householdId));
  }
}
