import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/api_problem.dart';
import 'package:moisture_controller/data/models.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';
import 'package:moisture_controller/features/devices/battery_card.dart';

import 'test_app.dart';

void main() {
  group('fake repository', () {
    late FakeMoistureRepository repo;
    setUp(() => repo = FakeMoistureRepository(latency: Duration.zero, role: Role.owner));
    tearDown(() => repo.dispose());

    test('the demo devices show every battery state', () async {
      final states = {for (final d in await repo.devices()) d.name: d.battery!.state};
      expect(states['Kitchen window'], BatteryState.ok);
      expect(states['Bathroom shelf'], BatteryState.absent);
      expect(states['Balcony'], BatteryState.low);
      expect(states['Office'], BatteryState.critical);
    });

    test('calibration scales the voltage, and refuses more than 10 % off', () async {
      final before = (await repo.devices()).firstWhere((d) => d.id == 'd1').battery!;
      expect(before.mv, 3900);
      await repo.calibrateBattery('d1', 3990);
      final after = (await repo.devices()).firstWhere((d) => d.id == 'd1').battery!;
      expect(after.mv, 3990);
      expect(after.calibrated, isTrue);
      await expectLater(
        repo.calibrateBattery('d1', 5000),
        throwsA(isA<ApiProblem>().having((e) => e.detail, 'detail', contains('10 %'))),
      );
      await expectLater(repo.calibrateBattery('d2', 3800), throwsA(isA<ApiProblem>()));
    });

    test('thresholds: critical must be below low', () async {
      await expectLater(repo.updateInstallation(batteryLowMv: 3400, batteryCriticalMv: 3500), throwsA(isA<ApiProblem>()));
      final i = await repo.updateInstallation(batteryLowMv: 3700, batteryCriticalMv: 3450);
      expect((i.batteryLowMv, i.batteryCriticalMv), (3700, 3450));
    });

    test('history ends at the current voltage, none without a cell', () async {
      final points = await repo.batteryHistory('d1', ChartRange.week);
      expect(points.last.mv, closeTo(3900, 20));
      expect(points.first.mv, greaterThan(points.last.mv));
      expect(await repo.batteryHistory('d2', ChartRange.week), isEmpty);
    });
  });

  testWidgets('plant cards: a battery chip with the estimate, none without a cell', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    // Monstera / Basil sit on d1 (ok, 67 %), Ficus on d2 (USB only), Geranium on d3 (low)
    expect(find.textContaining('about 67 %'), findsWidgets);
    expect(find.textContaining('about 28 %'), findsOneWidget, reason: 'the low cell of Balcony');
    expect(find.byIcon(Icons.battery_full), findsWidgets);
    expect(find.byIcon(Icons.battery_2_bar), findsOneWidget);
  });

  testWidgets('devices list: chips per state, no chip without a cell', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await openTab(tester, 'Devices');
    expect(find.byIcon(Icons.battery_full), findsNWidgets(2)); // Kitchen window and Greenhouse (both ok)
    expect(find.byIcon(Icons.battery_2_bar), findsOneWidget);  // Balcony
    expect(find.byIcon(Icons.battery_alert), findsOneWidget);  // Office
    // Bathroom shelf has no cell, so four of the five devices carry a chip
    expect(find.textContaining('about'), findsNWidgets(4));
  });

  testWidgets('device detail: battery card with state, volts, history and the calibration dialog', (tester) async {
    tallScreen(tester);
    final repo = await pumpApp(tester);
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Kitchen window'));
    await tester.pumpAndSettle();
    expect(find.text('Battery'), findsWidgets);
    expect(find.text('OK'), findsOneWidget);
    expect(find.text('3.90 V'), findsOneWidget);
    expect(find.byType(BatteryChart), findsOneWidget);
    expect(find.text('Calibrate battery'), findsOneWidget);

    await tester.tap(find.text('Calibrate battery'));
    await tester.pumpAndSettle();
    expect(find.textContaining('The module reports 3.90 V now'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Measured voltage'), '3,99');
    await tester.tap(find.widgetWithText(FilledButton, 'Calibrate'));
    await tester.pumpAndSettle();
    expect(find.text('Calibration sent to the device.'), findsOneWidget);
    expect((await repo.devices()).firstWhere((d) => d.id == 'd1').battery!.mv, 3990);
    expect(find.text('3.99 V'), findsOneWidget);
    expect(find.textContaining('Calibrated (+'), findsOneWidget);
  });

  testWidgets('calibration far off shows the hub error and changes nothing', (tester) async {
    tallScreen(tester);
    final repo = await pumpApp(tester);
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Kitchen window'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Calibrate battery'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Measured voltage'), '5.00');
    await tester.tap(find.widgetWithText(FilledButton, 'Calibrate'));
    await tester.pumpAndSettle();
    expect(find.textContaining('10 %'), findsWidgets);
    expect((await repo.devices()).firstWhere((d) => d.id == 'd1').battery!.mv, 3900);
  });

  testWidgets('a viewer and a member see the battery but cannot calibrate', (tester) async {
    tallScreen(tester);
    await pumpApp(tester, role: Role.member);
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Kitchen window'));
    await tester.pumpAndSettle();
    expect(find.text('3.90 V'), findsOneWidget);
    expect(find.text('Calibrate battery'), findsNothing);
  });

  testWidgets('a device without a cell: the card says so and has no chart or calibration', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Bathroom shelf'));
    await tester.pumpAndSettle();
    expect(find.text('No battery'), findsOneWidget);
    expect(find.byType(BatteryChart), findsNothing);
    expect(find.text('Calibrate battery'), findsNothing);
  });

  testWidgets('installation: the critical threshold is validated by the hub and applied', (tester) async {
    tallScreen(tester);
    final repo = await pumpApp(tester);
    goTo(tester, '/settings/installation');
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, 'Battery low (mV)'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Battery critical (mV)'), findsOneWidget);
    expect(find.textContaining('Applied to all devices'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Battery critical (mV)'), '3700');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(find.textContaining('battery thresholds'), findsWidgets);
    expect((await repo.installation()).batteryCriticalMv, 3400);

    await tester.enterText(find.widgetWithText(TextField, 'Battery critical (mV)'), '3450');
    await tester.enterText(find.widgetWithText(TextField, 'Battery low (mV)'), '3700');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    final i = await repo.installation();
    expect((i.batteryLowMv, i.batteryCriticalMv), (3700, 3450));
  });

  testWidgets('alerts: a critical battery has its own title and icon', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await openTab(tester, 'Alerts');
    expect(find.text('Office: battery critical'), findsOneWidget);
    expect(find.byIcon(Icons.battery_alert), findsWidgets);
  });

  testWidgets('water now on a module whose battery is critical warns, the module still decides', (tester) async {
    tallScreen(tester);
    final repo = await pumpApp(tester);
    await repo.updateInstallation(batteryLowMv: 3700, batteryCriticalMv: 3600); // Balcony (3.55 V) becomes critical
    goTo(tester, '/plants');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Geranium'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Water now'));
    await tester.pumpAndSettle();
    expect(find.textContaining("battery is critical"), findsOneWidget);
    expect(find.textContaining('Water for'), findsOneWidget, reason: 'the button stays enabled');
  });
}
