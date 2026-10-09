import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/app/router.dart';

import 'widget_test.dart' show pumpApp;

Future<void> openGateway(WidgetTester tester, {String household = 'h1'}) async {
  tester.view.physicalSize = const Size(1200, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await pumpApp(tester, household: household);
  await tester.tap(find.text('Settings'));
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(ListTile, 'Gateway'));
  await tester.pumpAndSettle();
}

void main() {
  test(
    'deep link /gateway#u=<code> opens the gateway screen with the code',
    () {
      expect(
        initialLocation(
          Uri.parse('https://app.example.com/gateway#u=K7QM-2XPA'),
        ),
        '/settings/gateway?code=K7QM-2XPA',
      );
      expect(initialLocation(Uri.parse('https://app.example.com/')), '/plants');
    },
  );

  testWidgets('shows gateway state and the update notice', (tester) async {
    await openGateway(tester);
    expect(find.text('gw-4k9m2x7q1v8w3h5t'), findsOneWidget);
    expect(find.text('Settings in sync'), findsOneWidget);
    expect(find.text('Update available: 0.2.0'), findsOneWidget);
    expect(find.text('192.168.1.20:8883'), findsOneWidget);
    expect(find.text('esp32-mqtt'), findsOneWidget);
    expect(find.text('Remove gateway'), findsOneWidget);
  });

  testWidgets('viewer sees an offline gateway but cannot manage it', (
    tester,
  ) async {
    await openGateway(tester, household: 'h2');
    expect(find.textContaining('Offline since'), findsOneWidget);
    expect(find.text('Remove gateway'), findsNothing);
    expect(find.text('Edit'), findsNothing);
  });

  testWidgets('remove, then add a gateway again with its code', (tester) async {
    await openGateway(tester);

    await tester.tap(find.text('Remove gateway'));
    await tester.pumpAndSettle();
    expect(find.text('Remove the gateway?'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Remove gateway'));
    await tester.pumpAndSettle();
    expect(find.text('Connect your plants'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'ABC');
    await tester.tap(find.widgetWithText(FilledButton, 'Add gateway'));
    await tester.pumpAndSettle();
    expect(find.textContaining('8-character code'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'k7qm-2xpa');
    await tester.tap(find.widgetWithText(FilledButton, 'Add gateway'));
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Waiting for the gateway to connect'), findsOneWidget);
    // Devices must be re-paired after the gateway change.
    expect(find.text('Devices to re-pair'), findsOneWidget);

    // The simulated gateway connects after 3 s and syncs after 5 s (live events).
    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Syncing settings'), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Settings in sync'), findsOneWidget);
    await tester.pumpAndSettle();
  });
}
