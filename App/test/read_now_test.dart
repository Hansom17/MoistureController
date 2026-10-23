import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/api_problem.dart';
import 'package:moisture_controller/data/models.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';

import 'test_app.dart';

void main() {
  group('fake repository', () {
    late FakeMoistureRepository repo;
    tearDown(() => repo.dispose());

    test('report now makes the readings of the device\'s plants fresh', () async {
      repo = FakeMoistureRepository(latency: Duration.zero, role: Role.member);
      final before = (await repo.plants()).firstWhere((p) => p.id == 'p2');
      expect(DateTime.now().difference(before.lastReadingAt!).inMinutes, greaterThanOrEqualTo(2));
      await repo.deviceAction('d1', DeviceAction.reportNow);
      final after = (await repo.plants()).firstWhere((p) => p.id == 'p2');
      expect(DateTime.now().difference(after.lastReadingAt!).inSeconds, lessThan(5));
      final other = (await repo.plants()).firstWhere((p) => p.id == 'p3'); // another device: untouched
      expect(DateTime.now().difference(other.lastReadingAt!).inSeconds, greaterThan(30));
    });

    test('a member may ask for a reading, a viewer may not, a member may still not reboot', () async {
      repo = FakeMoistureRepository(latency: Duration.zero, role: Role.viewer);
      await expectLater(repo.deviceAction('d1', DeviceAction.reportNow), throwsA(isA<ApiProblem>()));
      repo.dispose();
      repo = FakeMoistureRepository(latency: Duration.zero, role: Role.member);
      await repo.deviceAction('d1', DeviceAction.reportNow);
      await expectLater(repo.deviceAction('d1', DeviceAction.reboot), throwsA(isA<ApiProblem>()));
    });
  });

  testWidgets('plant page: "Read now" asks the module and the reading turns fresh', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await tester.tap(find.text('Basil'));
    await tester.pumpAndSettle();
    expect(find.textContaining('3 min ago'), findsWidgets);
    expect(find.byTooltip('Read now'), findsOneWidget);
    await tester.tap(find.byTooltip('Read now'));
    await tester.pumpAndSettle();
    expect(find.text('Reading requested. It arrives in a few seconds.'), findsOneWidget);
    expect(find.textContaining('Last reading just now'), findsOneWidget);
  });

  testWidgets('plant page: a viewer cannot ask for a reading, an offline module cannot either', (tester) async {
    tallScreen(tester);
    await pumpApp(tester, role: Role.viewer);
    await tester.tap(find.text('Basil'));
    await tester.pumpAndSettle();
    expect(tester.widget<IconButton>(find.widgetWithIcon(IconButton, Icons.refresh)).onPressed, isNull);
  });

  testWidgets('plant page: the offline device\'s plant has the button disabled', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await tester.tap(find.text('Aloe')); // on Office, offline
    await tester.pumpAndSettle();
    expect(tester.widget<IconButton>(find.widgetWithIcon(IconButton, Icons.refresh)).onPressed, isNull);
  });

  testWidgets('device detail has a Read now button next to Identify', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Kitchen window'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(OutlinedButton, 'Identify'), findsOneWidget);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Read now'));
    await tester.pumpAndSettle();
    expect(find.text('Sent to the device.'), findsOneWidget);
  });

  testWidgets('dashboard: the plant card menu has "Read now" and it asks the module', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await tester.tap(find.byTooltip('Plant menu').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Read now'));
    await tester.pumpAndSettle();
    expect(find.text('Reading requested. It arrives in a few seconds.'), findsOneWidget);
  });

  testWidgets('plant page: the menu in the app bar has "Read now"', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await tester.tap(find.text('Basil'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Plant menu'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Read now').last);
    await tester.pumpAndSettle();
    expect(find.text('Reading requested. It arrives in a few seconds.'), findsOneWidget);
  });
}
