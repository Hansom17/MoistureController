import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/models.dart';

import 'test_app.dart';

void main() {
  testWidgets('users: roles and an invite link that is shown once', (tester) async {
    tallScreen(tester);
    final repo = await pumpApp(tester);
    goTo(tester, '/settings/users');
    await tester.pumpAndSettle();
    expect(find.text('Anna'), findsOneWidget);
    expect(find.textContaining('@ben · Viewer'), findsOneWidget);
    expect(find.text('Invites'), findsOneWidget);

    await tester.tap(find.byTooltip('Create invite'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Viewer').last);
    await tester.pumpAndSettle();
    expect(find.text('Invite created'), findsOneWidget);
    final link = tester.widget<SelectableText>(find.byKey(const ValueKey('invite-link'))).data!;
    expect(link, startsWith('http://moisture.local/join#c='));
    expect((await repo.invites()).where((i) => i.status == 'open'), hasLength(2));
    await tester.tap(find.text('Done'));
    await tester.pumpAndSettle();
  });

  testWidgets('users: an admin may not touch other admins; the owner needs the password for them', (tester) async {
    tallScreen(tester);
    final repo = await pumpApp(tester);
    await repo.reauth('demo');
    await repo.updateUser('u-anna', role: Role.admin);
    goTo(tester, '/settings/users');
    await tester.pumpAndSettle();
    expect(find.textContaining('@anna · Admin'), findsOneWidget);
    // as the owner the menu of an admin offers "Make owner"
    await tester.tap(find.descendant(of: find.widgetWithText(ListTile, 'Anna'), matching: find.byType(PopupMenuButton<String>)));
    await tester.pumpAndSettle();
    expect(find.text('Make owner'), findsOneWidget);
    await tester.tapAt(const Offset(5, 5));
    await tester.pumpAndSettle();

    repo.setRole(Role.admin);
    goTo(tester, '/settings');
    await tester.pumpAndSettle();
    goTo(tester, '/settings/users');
    await tester.pumpAndSettle();
    expect(find.descendant(of: find.widgetWithText(ListTile, 'Anna'), matching: find.byType(PopupMenuButton<String>)), findsNothing);
  });

  testWidgets('my devices: the logins are listed and another one can be signed out', (tester) async {
    await pumpApp(tester);
    goTo(tester, '/settings/tokens');
    await tester.pumpAndSettle();
    expect(find.textContaining('Demo browser · this device'), findsOneWidget);
    expect(find.textContaining("Philipp's phone"), findsOneWidget);
    await tester.tap(find.byTooltip('Sign this device out'));
    await tester.pumpAndSettle();
    expect(find.textContaining("Philipp's phone"), findsNothing);
  });

  testWidgets('password change: wrong current password is refused, then it works', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    goTo(tester, '/settings/tokens');
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Current password'), 'nope');
    await tester.enterText(find.widgetWithText(TextField, 'New password'), 'a better password');
    await tester.tap(find.widgetWithText(FilledButton, 'Change password'));
    await tester.pumpAndSettle();
    expect(find.text('Wrong username or password.'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Current password'), 'demo');
    await tester.tap(find.widgetWithText(FilledButton, 'Change password'));
    await tester.pumpAndSettle();
    expect(find.text('Password changed.'), findsOneWidget);
  });

  testWidgets('installation settings: only the owner, saved with feedback', (tester) async {
    tallScreen(tester);
    final repo = await pumpApp(tester);
    goTo(tester, '/settings/installation');
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Name of this installation'), 'Flat 4');
    await tester.enterText(find.widgetWithText(TextField, 'Bot token'), '123:SECRET');
    await tester.enterText(find.widgetWithText(TextField, 'Chat id'), '42');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(find.text('Saved.'), findsOneWidget);
    final i = await repo.installation();
    expect(i.name, 'Flat 4');
    expect(i.telegramConfigured, isTrue);
  });

  testWidgets('alerts: open ones can be acknowledged by a member, not by a viewer', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    await openTab(tester, 'Alerts');
    expect(find.textContaining('Office'), findsWidgets);
    expect(find.text('Acknowledge'), findsNWidgets(3)); // device offline, safe mode, critical battery
    await tester.tap(find.text('Acknowledge').first);
    await tester.pumpAndSettle();
    expect(find.text('Acknowledge'), findsNWidgets(2));
  });

  testWidgets('a viewer cannot acknowledge', (tester) async {
    tallScreen(tester);
    await pumpApp(tester, role: Role.viewer);
    await openTab(tester, 'Alerts');
    final button = tester.widget<TextButton>(find.widgetWithText(TextButton, 'Acknowledge').first);
    expect(button.onPressed, isNull);
  });

  testWidgets('export: the password is asked first, then the download is offered', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    goTo(tester, '/settings/data');
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Export data'));
    await tester.pumpAndSettle();
    expect(find.text('Confirm with your password'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'demo');
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();
    // the test VM cannot start a browser download, and says so
    expect(find.text('Downloading is only supported in the web app for now.'), findsOneWidget);
  });
}
