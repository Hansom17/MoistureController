import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/app/app.dart';
import 'package:moisture_controller/core/session.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';

import 'test_app.dart';

void main() {
  testWidgets('dashboard: the button switches the gauges from percent to the measured value and back', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    expect(find.text('47%'), findsOneWidget); // Basil
    expect(find.byTooltip('Show measured values'), findsOneWidget);
    await tester.tap(find.byTooltip('Show measured values'));
    await tester.pumpAndSettle();
    expect(find.text('47%'), findsNothing);
    expect(find.text('${fakeRaw(47)}'), findsOneWidget);
    expect(find.byTooltip('Show percent'), findsOneWidget);
    await tester.tap(find.byTooltip('Show percent'));
    await tester.pumpAndSettle();
    expect(find.text('47%'), findsOneWidget);
  });

  testWidgets('plant page: measured gauge, the calibrated percent next to it and a chart on the raw scale', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await tester.tap(find.text('Basil'));
    await tester.pumpAndSettle();
    expect(find.text('Measured value ${fakeRaw(47)}'), findsOneWidget); // percent mode: the raw value as a hint
    await tester.tap(find.byTooltip('Show measured values'));
    await tester.pumpAndSettle();
    expect(find.text('${fakeRaw(47)}'), findsOneWidget);
    expect(find.text('Calibrated: 47 %'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the choice is remembered', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await tester.tap(find.byTooltip('Show measured values'));
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(tester.element(find.byType(MoistureApp)));
    expect(container.read(sharedPreferencesProvider).getString('value_mode'), 'measured');
  });
}
