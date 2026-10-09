import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/app/app.dart';
import 'package:moisture_controller/core/session.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';
import 'package:moisture_controller/features/pairing/label_scanner.dart';
import 'package:moisture_controller/features/pairing/pairing_controller.dart';
import 'package:moisture_controller/features/pairing/protocol/pairing_transport.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'pairing_controller_test.dart' show FakeDevice;

const goodLabel = 'MCPOP1:MC-3F9A:000G40R40M30E209185GR38E1W';

Future<FakeMoistureRepository> pump(
  WidgetTester tester, {
  required FakeDevice device,
  String household = 'h1',
  Object? connectError,
}) async {
  tester.view.physicalSize = const Size(800, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues({'last_household_id': household, 'locale': 'en'});
  final prefs = await SharedPreferences.getInstance();
  final repo = FakeMoistureRepository(latency: Duration.zero);
  addTearDown(repo.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        repositoryProvider.overrideWithValue(repo),
        sharedPreferencesProvider.overrideWithValue(prefs),
        // no camera in tests: a button "scans" the label
        labelScannerBuilderProvider.overrideWithValue(
          (onText) => Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextButton(onPressed: () => onText(goodLabel), child: const Text('fake scan')),
                TextButton(onPressed: () => onText('something else'), child: const Text('bad scan')),
              ],
            ),
          ),
        ),
        pairingConnectorProvider.overrideWithValue((label) async {
          if (connectError != null) throw connectError;
          return device;
        }),
        pairingPollIntervalProvider.overrideWithValue(const Duration(milliseconds: 10)),
        pairingOnlineTimeoutProvider.overrideWithValue(const Duration(milliseconds: 100)),
      ],
      child: const MoistureApp(),
    ),
  );
  await tester.pumpAndSettle();
  return repo;
}

/// Pumps until [finder] shows (progress indicators never "settle").
Future<void> until(WidgetTester tester, Finder finder) async {
  for (var i = 0; i < 100 && finder.evaluate().isEmpty; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
  expect(finder, findsWidgets);
}

Future<void> openWizard(WidgetTester tester) async {
  await tester.tap(find.text('Devices'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Add device'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('scan, name, choose the WiFi, test and finish', (tester) async {
    final device = FakeDevice();
    await pump(tester, device: device);
    await openWizard(tester);

    expect(find.text('Scan the device label'), findsOneWidget);
    await tester.tap(find.text('fake scan'));
    await tester.pumpAndSettle();

    expect(find.text('Name your device'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'Kitchen window');
    await tester.tap(find.text('Start pairing'));
    await until(tester, find.text('Choose the WiFi for the device'));

    // the networks the device found are listed; tapping one fills in the name
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Guest'), findsOneWidget);
    await tester.tap(find.widgetWithText(ListTile, 'Home'));
    await tester.pump();
    await tester.enterText(find.widgetWithText(TextField, 'WiFi password'), 'secret');
    await tester.tap(find.text('Connect and test'));
    await until(tester, find.textContaining('has not reported in yet'));

    expect(device.ssid, 'Home');
    expect(device.password, 'secret');
    expect(device.committed, isTrue);
    expect(find.text('Open device'), findsOneWidget);
  });

  testWidgets('a failed test shows the reason and lets the user try again', (tester) async {
    final device = FakeDevice(mqttOk: false);
    await pump(tester, device: device);
    await openWizard(tester);
    await tester.tap(find.text('fake scan'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Kitchen');
    await tester.tap(find.text('Start pairing'));
    await until(tester, find.text('Choose the WiFi for the device'));
    await tester.enterText(find.widgetWithText(TextField, 'Network name'), 'Home');
    await tester.tap(find.text('Connect and test'));
    await until(tester, find.textContaining('could not reach the gateway'));
    expect(find.textContaining('broker: error -5'), findsOneWidget);
    expect(device.committed, isFalse);
    expect(find.text('Connect and test'), findsOneWidget, reason: 'back at the WiFi step');
  });

  testWidgets('manual entry validates the code', (tester) async {
    await pump(tester, device: FakeDevice());
    await openWizard(tester);
    await tester.tap(find.text('Enter the code by hand'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Name on the label (MC-XXXX)'), 'MC-3F9A');
    await tester.enterText(find.widgetWithText(TextField, 'Code (26 characters)'), 'TOOSHORT');
    await tester.tap(find.text('Continue'));
    await tester.pump();
    expect(find.text('That is not a MoistureController label.'), findsOneWidget);
    await tester.enterText(
      find.widgetWithText(TextField, 'Code (26 characters)'),
      '000G40R40M30E209185GR38E1W',
    );
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Name your device'), findsOneWidget);
  });

  testWidgets('a scan of something else is refused', (tester) async {
    await pump(tester, device: FakeDevice());
    await openWizard(tester);
    await tester.tap(find.text('bad scan'));
    await tester.pump();
    expect(find.text('That is not a MoistureController label.'), findsOneWidget);
    expect(find.text('Scan the device label'), findsOneWidget);
  });

  testWidgets('no gateway: says so and keeps the device untouched', (tester) async {
    final device = FakeDevice();
    final repo = await pump(tester, device: device);
    await repo.removeGateway('h1');
    await openWizard(tester);
    await tester.tap(find.text('fake scan'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Kitchen');
    await tester.tap(find.text('Start pairing'));
    await until(tester, find.textContaining('Add a gateway'));
    expect(device.calls, isEmpty);
  });

  testWidgets('device not found offers a retry and the BOOT hint', (tester) async {
    await pump(tester, device: FakeDevice(), connectError: const DeviceNotFoundException('MC-3F9A'));
    await openWizard(tester);
    await tester.tap(find.text('fake scan'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Kitchen');
    await tester.tap(find.text('Start pairing'));
    await until(tester, find.textContaining('BOOT button held for 3 seconds'));
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('a viewer cannot add devices', (tester) async {
    await pump(tester, device: FakeDevice(), household: 'h2');
    await tester.tap(find.text('Devices'));
    await tester.pumpAndSettle();
    expect(find.text('Add device'), findsNothing);
  });

  testWidgets('closing in the middle asks, and cancelling removes the device', (tester) async {
    final device = FakeDevice();
    final repo = await pump(tester, device: device);
    await openWizard(tester);
    await tester.tap(find.text('fake scan'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Kitchen');
    await tester.tap(find.text('Start pairing'));
    await until(tester, find.text('Choose the WiFi for the device'));
    final before = (await repo.devices('h1')).length;

    await tester.tap(find.byType(CloseButton));
    await tester.pumpAndSettle();
    expect(find.text('Cancel pairing?'), findsOneWidget);
    await tester.tap(find.text('Keep going'));
    await tester.pumpAndSettle();
    expect(find.text('Choose the WiFi for the device'), findsOneWidget);

    await tester.tap(find.byType(CloseButton));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Cancel'));
    await tester.pumpAndSettle();
    expect((await repo.devices('h1')).length, before - 1);
    expect(device.aborted, isTrue);
    expect(find.text('Add device'), findsOneWidget, reason: 'back on the devices screen');
  });
}
