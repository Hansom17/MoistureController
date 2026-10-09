import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/models.dart';

import 'test_app.dart';

void main() {
  testWidgets('gateway status: services, versions and the backup button', (tester) async {
    tallScreen(tester);
    await pumpApp(tester);
    goTo(tester, '/settings/gateway');
    await tester.pumpAndSettle();
    expect(find.text('Watering service'), findsOneWidget);
    expect(find.text('SONOFF Dongle Plus MG24'), findsOneWidget);
    expect(find.text('Back up now'), findsOneWidget);
    await tester.tap(find.text('Back up now'));
    await tester.pumpAndSettle();
    expect(find.text('Backup written on the gateway.'), findsOneWidget);
  });

  testWidgets('Zigbee down shows in the status and a viewer cannot back up', (tester) async {
    tallScreen(tester);
    final repo = await pumpApp(tester, role: Role.viewer);
    repo.setZigbee('offline');
    goTo(tester, '/settings/gateway');
    await tester.pumpAndSettle();
    expect(find.text('Offline'), findsOneWidget);
    expect(find.text('Back up now'), findsNothing);
  });
}
