import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/models.dart';
import 'app_data.dart';
import 'session.dart';

/// Write operations. Screens call these instead of the repository; each one
/// refreshes the affected providers (live events refresh them again later).
final actionsProvider = Provider<Actions>(Actions.new);

class Actions {
  Actions(this._ref);

  final Ref _ref;

  Future<Command> waterNow(String plantId, int seconds) async {
    final command = await _ref.read(repositoryProvider).waterNow(plantId, seconds);
    _ref.invalidate(commandsProvider(plantId));
    return command;
  }

  Future<void> cancelCommand(Command command) async {
    await _ref.read(repositoryProvider).cancelCommand(command.id);
    _ref.invalidate(commandsProvider(command.plantId));
  }

  Future<void> saveRule(Rule rule) async {
    await _ref.read(repositoryProvider).saveRule(rule);
    _ref.invalidate(rulesProvider(rule.plantId));
  }

  Future<void> deleteRule(Rule rule) async {
    await _ref.read(repositoryProvider).deleteRule(rule);
    _ref.invalidate(rulesProvider(rule.plantId));
  }

  Future<Plant> createPlant({
    required String name,
    SlotRef sensor = const SlotRef(),
    SlotRef pump = const SlotRef(),
  }) async {
    final p = await _ref.read(repositoryProvider).createPlant(name: name, sensor: sensor, pump: pump);
    _ref.invalidate(plantsProvider);
    return p;
  }

  Future<void> updatePlant(String id, {String? name, String? notes, SlotRef? sensor, SlotRef? pump}) async {
    await _ref
        .read(repositoryProvider)
        .updatePlant(id, name: name, notes: notes, sensor: sensor, pump: pump);
    _ref.invalidate(plantsProvider);
  }

  Future<void> deletePlant(String id) async {
    await _ref.read(repositoryProvider).deletePlant(id);
    _ref.invalidate(plantsProvider);
  }

  Future<void> renameDevice(String id, String name) async {
    await _ref.read(repositoryProvider).renameDevice(id, name);
    _ref.invalidate(devicesProvider);
  }

  Future<void> saveDeviceConfig(String id, int baseRev, DeviceConfigBody config) async {
    await _ref.read(repositoryProvider).saveDeviceConfig(id, baseRev, config);
    _ref.invalidate(devicesProvider);
    _ref.invalidate(deviceConfigProvider(id));
  }

  Future<void> deleteDevice(String id, {bool force = false}) async {
    await _ref.read(repositoryProvider).deleteDevice(id, force: force);
    _ref.invalidate(devicesProvider);
    _ref.invalidate(plantsProvider);
  }

  Future<void> deviceAction(String id, DeviceAction action) async {
    await _ref.read(repositoryProvider).deviceAction(id, action);
    _ref.invalidate(devicesProvider);
  }

  Future<void> openJoin({String? installCode}) async {
    await _ref.read(repositoryProvider).openJoin(installCode: installCode);
    _ref.invalidate(joinStateProvider);
  }

  Future<void> closeJoin() async {
    await _ref.read(repositoryProvider).closeJoin();
    _ref.invalidate(joinStateProvider);
  }

  Future<void> acknowledgeAlert(String alertId) async {
    await _ref.read(repositoryProvider).acknowledgeAlert(alertId);
    _ref.invalidate(alertsProvider);
  }

  // ---- people ------------------------------------------------------------------------------

  Future<void> updateUser(String id, {Role? role, String? displayName, bool? disabled}) async {
    await _ref.read(repositoryProvider).updateUser(id, role: role, displayName: displayName, disabled: disabled);
    _ref.invalidate(usersProvider);
  }

  Future<void> deleteUser(String id) async {
    await _ref.read(repositoryProvider).deleteUser(id);
    _ref.invalidate(usersProvider);
  }

  Future<void> transferOwnership(String id) async {
    await _ref.read(repositoryProvider).transferOwnership(id);
    _ref.invalidate(usersProvider);
    await _ref.read(sessionProvider.notifier).refresh();
  }

  Future<CreatedInvite> createInvite(Role role) async {
    final created = await _ref.read(repositoryProvider).createInvite(role);
    _ref.invalidate(invitesProvider);
    return created;
  }

  Future<void> revokeInvite(String id) async {
    await _ref.read(repositoryProvider).revokeInvite(id);
    _ref.invalidate(invitesProvider);
  }

  Future<void> revokeToken(String id) async {
    await _ref.read(repositoryProvider).revokeToken(id);
    _ref.invalidate(tokensProvider);
  }

  Future<void> updateInstallation({
    String? name,
    String? timezone,
    int? batteryLowMv,
    String? telegramToken,
    String? telegramChatId,
  }) async {
    await _ref.read(repositoryProvider).updateInstallation(
      name: name,
      timezone: timezone,
      batteryLowMv: batteryLowMv,
      telegramToken: telegramToken,
      telegramChatId: telegramChatId,
    );
    _ref.invalidate(installationProvider);
    _ref.invalidate(metaProvider);
  }
}
