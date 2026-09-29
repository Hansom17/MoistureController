import '../data/models.dart';

/// Actions from the role matrix in PROJECT.md §3.2.
enum AppAction {
  viewData(Role.viewer),
  water(Role.member),
  editRules(Role.member),
  identifyDevice(Role.member),
  acknowledgeAlert(Role.member),
  manageDevices(Role.admin),
  manageMembers(Role.admin),
  manageHousehold(Role.owner);

  const AppAction(this.minRole);

  final Role minRole;
}

/// Mirrors the backend's role checks so the UI can hide or disable actions.
/// The backend stays the authority (App_Specs §8).
bool can(Role role, AppAction action) => role.index >= action.minRole.index;
