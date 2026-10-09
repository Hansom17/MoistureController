import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/app/app.dart';
import 'package:moisture_controller/app/router.dart';
import 'package:moisture_controller/core/session.dart';
import 'package:moisture_controller/data/models.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The whole app on the fake backend. [signedIn] stores the demo token like a returning visitor.
Future<FakeMoistureRepository> pumpApp(
  WidgetTester tester, {
  Role role = Role.owner,
  bool signedIn = true,
  bool setupRequired = false,
  Duration deviceDelay = const Duration(milliseconds: 500),
}) async {
  SharedPreferences.setMockInitialValues({'locale': 'en', if (signedIn) 'token': 'tok-0'});
  final prefs = await SharedPreferences.getInstance();
  final repo = FakeMoistureRepository(
    latency: Duration.zero,
    deviceDelay: deviceDelay,
    role: role,
    setupRequired: setupRequired,
  );
  addTearDown(repo.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [repositoryProvider.overrideWithValue(repo), sharedPreferencesProvider.overrideWithValue(prefs)],
      child: const MoistureApp(),
    ),
  );
  await tester.pumpAndSettle();
  return repo;
}

/// Opens a route as if the user had followed a link.
void goTo(WidgetTester tester, String location) {
  final container = ProviderScope.containerOf(tester.element(find.byType(MoistureApp)));
  container.read(routerProvider).go(location);
}

Future<void> openTab(WidgetTester tester, String label) async {
  final nav = find.byType(NavigationRail).evaluate().isNotEmpty ? find.byType(NavigationRail) : find.byType(NavigationBar);
  await tester.tap(find.descendant(of: nav, matching: find.text(label)));
  await tester.pumpAndSettle();
}

/// A tall window, so long lists are fully built and nothing has to be scrolled to.
void tallScreen(WidgetTester tester, {double height = 3200}) {
  tester.view.physicalSize = Size(800, height);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}
