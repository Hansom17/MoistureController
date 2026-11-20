import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/app/theme/app_theme.dart';
import 'package:moisture_controller/l10n/app_localizations.dart';
import 'package:moisture_controller/data/models.dart';
import 'package:moisture_controller/ui/status_chip.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';

import 'test_app.dart';

Future<FakeMoistureRepository> openEditor(WidgetTester tester, {Role role = Role.owner}) async {
  tallScreen(tester, height: 5200);
  final repo = await pumpApp(tester, role: role, deviceDelay: const Duration(milliseconds: 300));
  await openTab(tester, 'Devices');
  await tester.tap(find.text('Kitchen window'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Edit configuration'));
  await tester.pumpAndSettle();
  return repo;
}

void main() {
  testWidgets('config editor: the power mode is chosen, the matching field appears and it is saved', (tester) async {
    final repo = await openEditor(tester);
    expect(find.text('Power'), findsOneWidget);
    expect(find.text('For USB or mains power. The module listens all the time; commands arrive at once.'), findsOneWidget);
    expect(find.text('Check for messages every'), findsNothing);

    await tester.tap(find.text('Light sleep'));
    await tester.pumpAndSettle();
    expect(find.textContaining('commands arrive within a few seconds'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Check for messages every'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Check for messages every'), '100');
    await tester.pump();
    expect(find.text('Out of range'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Check for messages every'), '2000');
    await tester.pump();

    await tester.tap(find.text('Deep sleep'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, 'Listen after each report for'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Check for messages every'), findsNothing);
    await tester.tap(find.text('Light sleep'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    final saved = (await repo.deviceConfig('d1')).desired!;
    expect(saved.powerMode, PowerMode.lightSleep);
    expect(saved.pollIntervalMs, 2000);
    repo.dispose();
  });

  testWidgets('slot editor: the current reading becomes the dry or the wet point', (tester) async {
    final repo = await openEditor(tester);
    expect(find.text('Current reading: ${fakeRaw(18)}'), findsOneWidget); // Monstera on slot 1 of the Kitchen window
    await tester.tap(find.text('Use as dry').first);
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, '${fakeRaw(18)}'), findsOneWidget);
    await tester.tap(find.text('Use as wet').first);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    final s = (await repo.deviceConfig('d1')).desired!.slots.firstWhere((x) => x.slot == 0);
    expect(s.calDry, fakeRaw(18));
    expect(s.calWet, fakeRaw(18));
    repo.dispose();
  });

  testWidgets('device page: the sleep diagnostics only show for a module that sleeps', (tester) async {
    tallScreen(tester, height: 4200);
    final repo = await pumpApp(tester, deviceDelay: const Duration(milliseconds: 100));
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Kitchen window'));
    await tester.pumpAndSettle();
    expect(find.text('Always on'), findsOneWidget);
    expect(find.text('Last wake'), findsNothing);
    await tester.tap(find.text('Edit configuration'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Deep sleep'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pumpAndSettle();
    expect(find.text('Deep sleep'), findsWidgets);
    expect(find.text('Last wake'), findsOneWidget);
    expect(find.text('Next wake in'), findsOneWidget);
    repo.dispose();
  });

  testWidgets('a deep-sleep module between check-ins shows the sleeping status, not late', (tester) async {
    const d = Device(id: 'x', name: 'Shelf', status: DeviceStatus.sleeping, configSync: ConfigSync.inSync);
    expect(d.reachable, isTrue); // commands can be queued for it
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: AppTheme.light,
      home: Builder(builder: (context) => StatusChip.device(context, d)),
    ));
    expect(find.text('Sleeping'), findsOneWidget);
  });

  testWidgets('config editor: deep sleep with too short an interval is explained and cannot be saved', (tester) async {
    await openEditor(tester);
    await tester.tap(find.text('Deep sleep'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Deep sleep needs a report interval'), findsNothing); // 300 s is fine
    await tester.enterText(find.widgetWithText(TextField, 'Report interval'), '20');
    await tester.pump();
    expect(find.textContaining('Deep sleep needs a report interval'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Save')).onPressed, isNull);
    await tester.enterText(find.widgetWithText(TextField, 'Report interval'), '60');
    await tester.pump();
    expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Save')).onPressed, isNotNull);
  });

  testWidgets('Read now on a deep-sleep module says it answers at the next wake-up', (tester) async {
    tallScreen(tester, height: 5200);
    final repo = await pumpApp(tester, deviceDelay: const Duration(milliseconds: 100));
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Kitchen window'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit configuration'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Deep sleep'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pumpAndSettle();
    goTo(tester, '/plants/p2');
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 5)); // the "configuration sent" message is shown first
    await tester.pumpAndSettle();
    final btn = tester.widget<IconButton>(find.widgetWithIcon(IconButton, Icons.refresh));
    expect(btn.onPressed, isNotNull, reason: 'the refresh button is enabled');
    await tester.tap(find.byTooltip('Read now'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Reading requested'), findsOneWidget);
    expect(find.textContaining('answers when it wakes up next'), findsOneWidget);
    repo.dispose();
  });
}
