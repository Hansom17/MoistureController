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

  Future<NewDevice> createDevice(String householdId, String name) async {
    final created = await _ref
        .read(repositoryProvider)
        .createDevice(householdId, name);
    _ref.invalidate(devicesProvider(householdId));
    return created;
  }

  Future<PairingBundle> rekeyDevice(String householdId, String deviceId) =>
      _ref.read(repositoryProvider).rekeyDevice(householdId, deviceId);

  Future<void> deleteDevice(String householdId, String deviceId) async {
    await _ref.read(repositoryProvider).deleteDevice(householdId, deviceId);
    _ref.invalidate(devicesProvider(householdId));
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

  // --- gateway (App_Specs §12) ----------------------------------------------------------

  Future<GatewayInfo> claimGateway(String householdId, String userCode) async {
    final gateway = await _ref
        .read(repositoryProvider)
        .claimGateway(householdId, userCode);
    _gatewayChanged(householdId);
    return gateway;
  }

  Future<void> setGatewayLanHost(
    String householdId,
    String? lanHostOverride,
  ) async {
    await _ref
        .read(repositoryProvider)
        .setGatewayLanHost(householdId, lanHostOverride);
    _ref.invalidate(gatewayProvider(householdId));
  }

  Future<void> removeGateway(String householdId) async {
    await _ref.read(repositoryProvider).removeGateway(householdId);
    _gatewayChanged(householdId);
  }

  void _gatewayChanged(String householdId) {
    _ref.invalidate(gatewayProvider(householdId));
    _ref.invalidate(householdsProvider);
    _ref.invalidate(devicesProvider(householdId));
  }
}
