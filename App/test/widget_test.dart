import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/models.dart';

import 'test_app.dart';

void main() {
  testWidgets('dashboard lists the plants of the installation', (tester) async {
    await pumpApp(tester);
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Monstera'), findsOneWidget);
    expect(find.text('Basil'), findsOneWidget);
    expect(find.text('Tomatoes'), findsOneWidget);
    expect(find.text('Add plant'), findsOneWidget);
  });

  testWidgets('without a stored login the login screen opens, and signing in leads to the dashboard', (tester) async {
    await pumpApp(tester, signedIn: false);
    expect(find.text('Sign in to continue'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Username'), 'demo');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'demo');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Monstera'), findsOneWidget);
  });

  testWidgets('a wrong password shows an error and stays on the login screen', (tester) async {
    await pumpApp(tester, signedIn: false);
    await tester.enterText(find.widgetWithText(TextField, 'Username'), 'demo');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'nope');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Wrong username or password.'), findsOneWidget);
    expect(find.text('Monstera'), findsNothing);
  });

  testWidgets('first start: the setup screen creates the owner', (tester) async {
    await pumpApp(tester, signedIn: false, setupRequired: true);
    expect(find.text('Set up this gateway'), findsWidgets);
    await tester.enterText(find.widgetWithText(TextField, 'Setup code'), 'WRONG');
    await tester.enterText(find.widgetWithText(TextField, 'Username'), 'me');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'longpassword');
    await tester.ensureVisible(find.widgetWithText(FilledButton, 'Set up this gateway'));
    await tester.tap(find.widgetWithText(FilledButton, 'Set up this gateway'));
    await tester.pumpAndSettle();
    expect(find.text('The setup code is wrong.'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Setup code'), 'DEMOCODE');
    await tester.tap(find.widgetWithText(FilledButton, 'Set up this gateway'));
    await tester.pumpAndSettle();
    expect(find.text('Monstera'), findsOneWidget);
  });

  testWidgets('an invite link works without a login', (tester) async {
    await pumpApp(tester, signedIn: false);
    goTo(tester, '/join?code=DEMOINVITE');
    await tester.pumpAndSettle();
    expect(find.text('Join Home'), findsOneWidget);
    expect(find.text('You were invited as Member.'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Username'), 'newbie');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'longpassword');
    await tester.ensureVisible(find.widgetWithText(FilledButton, 'Create account'));
    await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
    await tester.pumpAndSettle();
    expect(find.text('Monstera'), findsOneWidget);
  });

  testWidgets('an invalid invite says so', (tester) async {
    await pumpApp(tester, signedIn: false);
    goTo(tester, '/join?code=NOPE');
    await tester.pumpAndSettle();
    expect(find.text('This invite is not valid (anymore).'), findsOneWidget);
  });

  testWidgets('member can water; command goes queued → running → done', (tester) async {
    await pumpApp(tester, role: Role.member, deviceDelay: const Duration(seconds: 3));
    await tester.tap(find.text('Basil'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Water now'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Water for 10 s'));
    // step by step: settling would let the simulated device run through its whole sequence
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Watering queued'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Queued'), 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('Queued'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3)); // the device picks it up
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 50)); // the spinner never settles
    }
    expect(find.textContaining('Running until'), findsOneWidget);

    await tester.pump(const Duration(seconds: 10));
    await tester.pumpAndSettle();
    expect(find.text('Done'), findsOneWidget);
  });

  testWidgets('viewer sees a disabled water button and no add buttons', (tester) async {
    await pumpApp(tester, role: Role.viewer);
    expect(find.text('Add plant'), findsNothing);
    await tester.tap(find.text('Basil'));
    await tester.pumpAndSettle();
    final button = tester.widget<ButtonStyleButton>(find.widgetWithText(FilledButton, 'Water now'));
    expect(button.onPressed, isNull);
  });

  testWidgets('wide layout: water sheet opens from the two-column detail', (tester) async {
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

  testWidgets('Zigbee down: a banner on the dashboard and no change of the devices', (tester) async {
    final repo = await pumpApp(tester);
    expect(find.textContaining('Zigbee is not running'), findsNothing);
    repo.setZigbee('offline');
    await tester.pumpAndSettle();
    expect(find.textContaining('Zigbee is not running'), findsOneWidget);
    repo.setZigbee('online');
    await tester.pumpAndSettle();
    expect(find.textContaining('Zigbee is not running'), findsNothing);
  });

  testWidgets('a new plant can be created from the dashboard', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text('Add plant'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Name'), 'Rosemary');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(find.text('Rosemary'), findsOneWidget);
  });

  testWidgets('rules: the detail shows the rule and why it did or did not water', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text('Monstera'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.textContaining('Below 25 %'), 300, scrollable: find.byType(Scrollable).first);
    await tester.tap(find.textContaining('Below 25 %'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.textContaining('Skipped: too soon'), 300, scrollable: find.byType(Scrollable).first);
    expect(find.textContaining('Skipped: too soon after the last watering'), findsOneWidget);
    expect(find.text('Watered'), findsOneWidget);
  });

  testWidgets('settings: sign out leads to the login screen; the demo role switch hides owner entries', (tester) async {
    await pumpApp(tester);
    await openTab(tester, 'Settings');
    expect(find.text('Users'), findsOneWidget);
    expect(find.text('Installation settings'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Member'), 300, scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('Member'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Sign out'), -300, scrollable: find.byType(Scrollable).first);
    expect(find.text('Users'), findsNothing);
    expect(find.text('Installation settings'), findsNothing);
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(find.text('Sign in to continue'), findsOneWidget);
  });
}
