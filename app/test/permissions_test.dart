import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/core/permissions.dart';
import 'package:moisture_controller/data/models.dart';

void main() {
  // PROJECT.md §3.2
  const matrix = {
    AppAction.viewData: [Role.owner, Role.admin, Role.member, Role.viewer],
    AppAction.water: [Role.owner, Role.admin, Role.member],
    AppAction.editRules: [Role.owner, Role.admin, Role.member],
    AppAction.manageDevices: [Role.owner, Role.admin],
    AppAction.manageMembers: [Role.owner, Role.admin],
    AppAction.manageHousehold: [Role.owner],
  };

  matrix.forEach((action, allowed) {
    test('$action', () {
      for (final role in Role.values) {
        expect(can(role, action), allowed.contains(role), reason: '$role');
      }
    });
  });
}
