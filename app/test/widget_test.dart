import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/app/app.dart';
import 'package:moisture_controller/core/session.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<FakeMoistureRepository> pumpApp(
  WidgetTester tester, {
  String household = 'h1',
}) async {
  SharedPreferences.setMockInitialValues({
    'last_household_id': household,
    'locale': 'en',
  });
  final prefs = await SharedPreferences.getInstance();
  final repo = FakeMoistureRepository(latency: Duration.zero);
  addTearDown(repo.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        repositoryProvider.overrideWithValue(repo),
        sharedPreferencesProvider.overrideWithValue(prefs),
      ],
      child: const MoistureApp(),
    ),
  );
  await tester.pumpAndSettle();
  return repo;
}

void main() {
  testWidgets('dashboard lists the plants of the current household', (
    tester,
  ) async {
    await pumpApp(tester);
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Basil'), findsOneWidget);
    expect(find.text('Monstera'), findsOneWidget);
    expect(find.text('Roses'), findsNothing);
  });

  testWidgets('hub-offline banner is shown for that household', (tester) async {
    await pumpApp(tester, household: 'h2');
    expect(find.textContaining('Hub offline since'), findsOneWidget);
    expect(find.text('Roses'), findsOneWidget);
  });

  testWidgets('member can water; command goes queued → running → done', (
    tester,
  ) async {
    await pumpApp(tester);
    await tester.tap(find.text('Basil'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Water now'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Water for 10 s'));
    await tester.pumpAndSettle();

    // Snackbar confirms, and the command list shows the live state.
    expect(find.text('Watering queued'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.textContaining('Queued ·'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('Queued ·'), findsOneWidget);

    // Device wakes after 5 s, picks it up and runs the pump for 10 s.
    await tester.pump(const Duration(seconds: 5));
    await tester.pump(const Duration(seconds: 1));
    // The running spinner never settles, so pump frames explicitly.
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 50));
    }
    expect(find.textContaining('Running until'), findsOneWidget);

    await tester.pump(const Duration(seconds: 10));
    await tester.pumpAndSettle();
    expect(find.text('Done'), findsNWidgets(2)); // new + seeded rule command
  });

  testWidgets('viewer sees a disabled water button', (tester) async {
    await pumpApp(tester, household: 'h2');
    await tester.tap(find.text('Roses'));
    await tester.pumpAndSettle();

    final button = tester.widget<ButtonStyleButton>(
      find.widgetWithText(FilledButton, 'Water now'),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('wide layout: water sheet opens from the two-column detail', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await pumpApp(tester);
    expect(find.byType(NavigationRail), findsOneWidget);

    await tester.tap(find.text('Basil'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Water now'));
    await tester.pumpAndSettle();
    expect(find.text('Water Basil'), findsOneWidget);
    expect(find.text('Pump limit: 30 s'), findsOneWidget);
  });
}
