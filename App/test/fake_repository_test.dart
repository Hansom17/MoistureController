import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/api_problem.dart';
import 'package:moisture_controller/data/models.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';

Matcher problem(String type) => throwsA(isA<ApiProblem>().having((p) => p.type, 'type', type));

void main() {
  late FakeMoistureRepository repo;

  FakeMoistureRepository make({Role role = Role.owner, bool setup = false}) => repo = FakeMoistureRepository(
    latency: Duration.zero,
    deviceDelay: const Duration(milliseconds: 20),
    role: role,
    setupRequired: setup,
  );

  setUp(make);
  tearDown(() => repo.dispose());

  test('viewer cannot water', () async {
    make(role: Role.viewer);
    await expectLater(repo.waterNow('p1', 5), problem(ApiProblem.forbidden));
  });

  test('watering above the pump limit is rejected', () async {
    await expectLater(repo.waterNow('p1', 31), problem(ApiProblem.safetyLimit));
  });

  test('a plant without a pump cannot be watered', () async {
    await expectLater(repo.waterNow('p5', 5), problem(ApiProblem.conflict));
  });

  test('command runs queued → running → done with events, and a second one is busy meanwhile', () async {
    final events = <LiveEventKind>[];
    final sub = repo.events().listen((e) => events.add(e.kind));
    final before = (await repo.plants()).firstWhere((p) => p.id == 'p1');

    final command = await repo.waterNow('p1', 1);
    expect(command.state, CommandState.queued);
    await expectLater(repo.waterNow('p1', 1), problem(ApiProblem.busy));

    await Future<void>.delayed(const Duration(milliseconds: 1300));
    final after = (await repo.commands('p1')).firstWhere((c) => c.id == command.id);
    expect(after.state, CommandState.done);
    final plant = (await repo.plants()).firstWhere((p) => p.id == 'p1');
    expect(plant.moisturePercent, greaterThan(before.moisturePercent!));
    expect(events, containsAllInOrder([LiveEventKind.command, LiveEventKind.reading]));
    await sub.cancel();
  });

  test('a command for an offline device stays queued until cancelled', () async {
    final plant = await repo.createPlant(
      name: 'Office fern',
      sensor: const SlotRef(deviceId: 'd4', slot: 0),
      pump: const SlotRef(deviceId: 'd4', slot: 2),
    );
    final c = await repo.waterNow(plant.id, 3);
    expect(c.sent, isFalse);
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect((await repo.commands(plant.id)).first.state, CommandState.queued);
    await repo.cancelCommand(c.id);
    expect((await repo.commands(plant.id)).first.state, CommandState.cancelled);
    await expectLater(repo.cancelCommand(c.id), problem(ApiProblem.conflict));
  });

  test('login, wrong password, sign out', () async {
    final session = await repo.login(username: 'anna', password: 'anna', deviceName: 'Phone');
    expect(session.user.role, Role.member);
    expect((await repo.tokens()).any((t) => t.name == 'Phone' && t.current), isTrue);
    await expectLater(repo.login(username: 'anna', password: 'nope'), problem(ApiProblem.invalidCredentials));
    await repo.logout();
    await expectLater(repo.me(), problem(ApiProblem.unauthorized));
  });

  test('first-time setup needs the right code and only works once', () async {
    make(setup: true);
    expect((await repo.meta()).setupRequired, isTrue);
    await expectLater(
      repo.setup(setupCode: 'WRONG', name: 'Flat', timezone: 'UTC', username: 'me', password: 'longpassword'),
      problem(ApiProblem.invalidSetupCode),
    );
    final s = await repo.setup(
      setupCode: 'democode', name: 'Flat', timezone: 'UTC', username: 'me', password: 'longpassword');
    expect(s.user.role, Role.owner);
    expect((await repo.meta()).name, 'Flat');
    await expectLater(
      repo.setup(setupCode: 'DEMOCODE', name: 'x', timezone: 'UTC', username: 'me2', password: 'longpassword'),
      problem(ApiProblem.alreadySetUp),
    );
  });

  test('invites: preview, accept once, then invalid', () async {
    final created = await repo.createInvite(Role.viewer);
    expect((await repo.previewInvite(created.code)).role, Role.viewer);
    final s = await repo.acceptInvite(code: created.code, username: 'newbie', password: 'longpassword');
    expect(s.user.role, Role.viewer);
    await expectLater(repo.previewInvite(created.code), problem(ApiProblem.invalidInvite));
  });

  test('sensitive actions need the password first', () async {
    await expectLater(repo.exportData(), problem(ApiProblem.reauthRequired));
    await expectLater(repo.reauth('wrong'), problem(ApiProblem.invalidCredentials));
    await repo.reauth('demo');
    expect(await repo.exportData(), isNotEmpty);
    await repo.transferOwnership('u-ben');
    expect((await repo.users()).firstWhere((u) => u.id == 'u-ben').role, Role.owner);
    expect((await repo.me()).role, Role.admin);
  });

  test('admins cannot change admins or make them', () async {
    make(role: Role.admin);
    await expectLater(repo.updateUser('u-anna', role: Role.admin), problem(ApiProblem.forbidden));
    expect((await repo.updateUser('u-anna', role: Role.viewer)).role, Role.viewer);
  });

  test('configuration: conflict on a stale revision, pending until the device confirms, port clash is rejected', () async {
    final d = (await repo.devices()).firstWhere((d) => d.id == 'd1');
    final cfg = (await repo.deviceConfig('d1')).desired!;
    await expectLater(repo.saveDeviceConfig('d1', d.desiredRev + 5, cfg), problem(ApiProblem.conflict));
    final clash = cfg.copyWith(slots: [
      const SlotConfig(slot: 0, module: 'moisture', port: 'P1'),
      const SlotConfig(slot: 1, module: 'moisture', port: 'P1'),
    ]);
    await expectLater(repo.saveDeviceConfig('d1', d.desiredRev, clash), problem(ApiProblem.validation));

    final rev = await repo.saveDeviceConfig('d1', d.desiredRev, cfg);
    expect(rev, d.desiredRev + 1);
    expect((await repo.devices()).firstWhere((x) => x.id == 'd1').configSync, ConfigSync.pending);
    await Future<void>.delayed(const Duration(milliseconds: 60));
    final now = (await repo.devices()).firstWhere((x) => x.id == 'd1');
    expect(now.configSync, ConfigSync.inSync);
    expect(now.reportedRev, rev);
  });

  test('join window: a device appears, goes through the steps and ends up online', () async {
    final join = await repo.openJoin(installCode: '83FED3407A9397389D3A6B1B1D8A7F34');
    expect(join.open, isTrue);
    await Future<void>.delayed(const Duration(milliseconds: 30));
    var state = await repo.joinState();
    expect(state.deviceIds, hasLength(1));
    final id = state.deviceIds.single;
    expect((await repo.devices()).firstWhere((d) => d.id == id).status, DeviceStatus.joining);
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect((await repo.devices()).firstWhere((d) => d.id == id).status, DeviceStatus.online);
    await repo.closeJoin();
    expect((await repo.joinState()).open, isFalse);
  });

  test('removing a device needs the password', () async {
    await expectLater(repo.deleteDevice('d1'), problem(ApiProblem.reauthRequired));
    await repo.reauth('demo');
    await repo.deleteDevice('d1');
    expect((await repo.devices()).any((d) => d.id == 'd1'), isFalse);
  });

  test('alerts: acknowledging moves them out of the open list', () async {
    expect((await repo.alerts()).where((a) => a.open), isNotEmpty);
    await repo.acknowledgeAlert('a1');
    expect((await repo.alerts()).firstWhere((a) => a.id == 'a1').open, isFalse);
  });
}
