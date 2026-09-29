import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/app/router.dart';

import 'widget_test.dart' show pumpApp;

Future<void> openHub(WidgetTester tester, {String household = 'h1'}) async {
  tester.view.physicalSize = const Size(1200, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await pumpApp(tester, household: household);
  await tester.tap(find.text('Settings'));
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(ListTile, 'Hub'));
  await tester.pumpAndSettle();
}

void main() {
  test('deep link /hub#u=<code> opens the hub screen with the code', () {
    expect(
      initialLocation(Uri.parse('https://app.example.com/hub#u=K7QM-2XPA')),
      '/settings/hub?code=K7QM-2XPA',
    );
    expect(initialLocation(Uri.parse('https://app.example.com/')), '/plants');
  });

  testWidgets('shows hub state and the update notice', (tester) async {
    await openHub(tester);
    expect(find.text('hub-4k9m2x7q1v8w3h5t'), findsOneWidget);
    expect(find.text('Settings in sync'), findsOneWidget);
    expect(find.text('Update available: 0.2.0'), findsOneWidget);
    expect(find.text('192.168.1.20'), findsOneWidget);
    expect(find.text('Remove hub'), findsOneWidget);
  });

  testWidgets('viewer sees an offline hub but cannot manage it', (tester) async {
    await openHub(tester, household: 'h2');
    expect(find.textContaining('Offline since'), findsOneWidget);
    expect(find.text('Remove hub'), findsNothing);
    expect(find.text('Edit'), findsNothing);
  });

  testWidgets('remove, then add a hub again with its code', (tester) async {
    await openHub(tester);

    await tester.tap(find.text('Remove hub'));
    await tester.pumpAndSettle();
    expect(find.text('Remove the hub?'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Remove hub'));
    await tester.pumpAndSettle();
    expect(find.text('Keep watering without internet'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'ABC');
    await tester.tap(find.widgetWithText(FilledButton, 'Add hub'));
    await tester.pumpAndSettle();
    expect(find.textContaining('8-character code'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'k7qm-2xpa');
    await tester.tap(find.widgetWithText(FilledButton, 'Add hub'));
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Waiting for the hub to connect'), findsOneWidget);
    // Devices must be re-paired after the gateway change.
    expect(find.text('Devices to re-pair'), findsOneWidget);

    // The simulated hub connects after 3 s and syncs after 5 s (live events).
    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Syncing settings'), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Settings in sync'), findsOneWidget);
    await tester.pumpAndSettle();
  });
}
