import '../data/models.dart';

/// Actions from the role matrix in PROJECT.md §3.2.
enum AppAction {
  viewData(Role.viewer),
  water(Role.member),
  editPlants(Role.member),
  editRules(Role.member),
  identifyDevice(Role.member),
  acknowledgeAlert(Role.member),
  manageDevices(Role.admin),
  manageUsers(Role.admin),
  backup(Role.admin),
  manageInstallation(Role.owner),
  exportData(Role.owner);

  const AppAction(this.minRole);

  final Role minRole;
}

/// Mirrors the api's role checks so the UI can hide or disable actions.
/// The api stays the authority (App/specs.md Part A §8).
bool can(Role role, AppAction action) => role.index >= action.minRole.index;
