import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/api_problem.dart';
import 'package:moisture_controller/data/models.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';

void main() {
  late FakeMoistureRepository repo;

  setUp(
    () => repo = FakeMoistureRepository(
      latency: Duration.zero,
      deviceDelay: const Duration(milliseconds: 20),
    ),
  );
  tearDown(() => repo.dispose());

  test('viewer cannot water', () async {
    expect(
      () => repo.waterNow('h2', 'p6', 5),
      throwsA(
        isA<ApiProblem>().having((p) => p.type, 'type', ApiProblem.forbidden),
      ),
    );
  });

  test('watering above the pump limit is rejected', () async {
    expect(
      () => repo.waterNow('h1', 'p1', 31),
      throwsA(
        isA<ApiProblem>().having((p) => p.type, 'type', ApiProblem.safetyLimit),
      ),
    );
  });

  test(
    'command runs queued → delivered → running → done with events',
    () async {
      final states = <LiveEventKind>[];
      final sub = repo.events('h1').listen((e) => states.add(e.kind));
      final before = (await repo.plants('h1')).firstWhere((p) => p.id == 'p1');

      final command = await repo.waterNow('h1', 'p1', 1);
      expect(command.state, CommandState.queued);

      await Future<void>.delayed(const Duration(milliseconds: 2300));
      final after = (await repo.commands(
        'h1',
        'p1',
      )).firstWhere((c) => c.id == command.id);
      expect(after.state, CommandState.done);
      final plant = (await repo.plants('h1')).firstWhere((p) => p.id == 'p1');
      expect(plant.moisturePercent, greaterThan(before.moisturePercent!));
      expect(
        states,
        containsAllInOrder([LiveEventKind.command, LiveEventKind.reading]),
      );
      await sub.cancel();
    },
  );

  test('only queued commands can be cancelled', () async {
    final c = await repo.waterNow('h1', 'p2', 3);
    await repo.cancelCommand('h1', c.id);
    final list = await repo.commands('h1', 'p2');
    expect(list.first.state, CommandState.cancelled);
    expect(() => repo.cancelCommand('h1', c.id), throwsA(isA<ApiProblem>()));
  });
}
