import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/models.dart';

import 'test_app.dart';

void main() {
  testWidgets('devices tab: status and config sync of every device', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await openTab(tester, 'Devices');
    expect(find.text('Kitchen window'), findsOneWidget);
    expect(find.text('Online'), findsWidgets);
    expect(find.textContaining('Late'), findsOneWidget);
    expect(find.textContaining('Safe mode'), findsOneWidget);
    expect(find.textContaining('Config pending (rev 8)'), findsOneWidget);
    expect(find.textContaining('port P3 cannot drive this module'), findsOneWidget);
    expect(find.text('Add device'), findsOneWidget);
  });

  testWidgets('a viewer cannot add devices', (tester) async {
    await pumpApp(tester, role: Role.viewer);
    await openTab(tester, 'Devices');
    expect(find.text('Add device'), findsNothing);
  });

  testWidgets('adding a device: open the window, the module joins and goes through the steps', (tester) async {
    await pumpApp(tester, deviceDelay: const Duration(seconds: 2));
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Add device'));
    await tester.pumpAndSettle();
    expect(find.text('Add a device'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Install code (optional)'), '83FED3407A9397389D3A6B1B1D8A7F34');
    await tester.tap(find.widgetWithText(FilledButton, 'Open join window'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Waiting for the module…'), findsOneWidget);
    expect(find.textContaining('Open for'), findsOneWidget);

    await tester.pump(const Duration(seconds: 2)); // the module joins
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Interviewing'), findsOneWidget);
    expect(find.text('Joining'), findsOneWidget);

    await tester.pump(const Duration(seconds: 2)); // interview done
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Waiting for first report'), findsOneWidget);

    await tester.pump(const Duration(seconds: 2)); // first report
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.widgetWithText(FilledButton, 'Name and configure'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Device name'), 'Windowsill');
    await tester.tap(find.widgetWithText(FilledButton, 'Name and configure'));
    await tester.pumpAndSettle();
    expect(find.text('Edit configuration'), findsWidgets); // the slot editor opened
  });

  testWidgets('device detail: diagnostics, slots and the safe-mode card', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Greenhouse'));
    await tester.pumpAndSettle();
    expect(find.text('Safe mode'), findsWidgets);
    expect(find.textContaining('crash_loop'), findsOneWidget);
    expect(find.text('Clear safe mode'), findsOneWidget);
    await tester.tap(find.text('Clear safe mode'));
    await tester.pumpAndSettle();
    expect(find.text('Clear safe mode'), findsNothing);
    expect(find.text('Diagnostics'), findsOneWidget);
    expect(find.text('Running for'), findsOneWidget);
    expect(find.text('1 d 0 h'), findsOneWidget);
  });

  testWidgets('removing a device asks for the password first', (tester) async {
    tallScreen(tester);
    final repo = await pumpApp(tester);
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Office'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Remove device'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Remove device'));
    await tester.pumpAndSettle();
    expect(find.text('Confirm with your password'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'wrong');
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();
    expect(find.text('Wrong username or password.'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'demo');
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();
    expect((await repo.devices()).any((d) => d.id == 'd4'), isFalse);
    expect(find.text('Office'), findsNothing);
  });

  testWidgets('slot editor: change the report interval and save; the device shows the pending revision', (tester) async {
    tallScreen(tester, height: 4200);
    final repo = await pumpApp(tester, deviceDelay: const Duration(seconds: 5));
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Kitchen window'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit configuration'));
    await tester.pumpAndSettle();

    expect(find.text('Report interval'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Report interval'), '5');
    await tester.pump();
    expect(find.text('Out of range'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Report interval'), '120');
    await tester.pump();
    expect(find.text('Out of range'), findsNothing);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    final d = (await repo.deviceConfig('d1'));
    expect(d.desired!.reportIntervalS, 120);
    expect(d.sync, ConfigSync.pending);
    expect(find.textContaining('Config pending'), findsWidgets);
    repo.dispose(); // the simulated device would confirm after the test is over
  });

  testWidgets('slot editor: a stale revision explains what happened', (tester) async {
    tallScreen(tester, height: 4200);
    final repo = await pumpApp(tester);
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Kitchen window'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit configuration'));
    await tester.pumpAndSettle();
    // somebody else saves first
    final cfg = (await repo.deviceConfig('d1')).desired!;
    await repo.saveDeviceConfig('d1', (await repo.deviceConfig('d1')).desiredRev, cfg);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Someone else changed this device'), findsOneWidget);
    repo.dispose();
  });

  testWidgets('a rejected configuration shows the device error and can go back to the running one', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await openTab(tester, 'Devices');
    await tester.tap(find.text('Office'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit configuration'));
    await tester.pumpAndSettle();
    expect(find.textContaining('port P3 cannot drive this module'), findsOneWidget);
    expect(find.text('Use the running configuration'), findsOneWidget);
  });
}
