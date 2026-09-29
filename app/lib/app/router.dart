import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/format.dart';
import '../core/household_data.dart';
import '../core/session.dart';
import '../features/alerts/alerts_screen.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/devices/device_detail_screen.dart';
import '../features/devices/devices_screen.dart';
import '../features/plants/plant_detail_screen.dart';
import '../features/gateway/gateway_screen.dart';
import '../features/settings/settings_screen.dart';
import 'theme/tokens.dart';

/// Deep links `/gateway#u=<code>` and `/join#c=<code>` (App_Specs §13) carry the
/// code in the URL fragment, which the router never sees; map them here.
String initialLocation(Uri url) {
  final path = url.path.endsWith('/') && url.path.length > 1
      ? url.path.substring(0, url.path.length - 1)
      : url.path;
  if (path.endsWith('/gateway') && url.fragment.startsWith('u=')) {
    return Uri(
      path: '/settings/gateway',
      queryParameters: {'code': url.fragment.substring(2)},
    ).toString();
  }
  return '/plants';
}

final routerProvider = Provider<GoRouter>((ref) {
  final router = GoRouter(
    initialLocation: initialLocation(Uri.base),
    routes: [
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => AppShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/plants',
                builder: (_, _) => const DashboardScreen(),
                routes: [
                  GoRoute(
                    path: ':plantId',
                    builder: (_, state) => PlantDetailScreen(
                      plantId: state.pathParameters['plantId']!,
                    ),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/devices',
                builder: (_, _) => const DevicesScreen(),
                routes: [
                  GoRoute(
                    path: ':deviceId',
                    builder: (_, state) => DeviceDetailScreen(
                      deviceId: state.pathParameters['deviceId']!,
                    ),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(path: '/alerts', builder: (_, _) => const AlertsScreen()),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/settings',
                builder: (_, _) => const SettingsScreen(),
                routes: [
                  GoRoute(
                    path: 'gateway',
                    builder: (_, state) => GatewayScreen(
                      initialCode: state.uri.queryParameters['code'],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

/// Bottom navigation on phones, navigation rail from 600 dp (App_Specs §9).
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.shell});

  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final householdId = ref.watch(currentHouseholdProvider).value?.id;
    final openAlerts = householdId == null
        ? 0
        : ref.watch(openAlertCountProvider(householdId));

    Widget alertIcon(IconData icon) => Badge(
      isLabelVisible: openAlerts > 0,
      label: Text('$openAlerts'),
      child: Icon(icon),
    );

    final destinations = [
      (Icons.yard_outlined, Icons.yard, l.navPlants),
      (Icons.sensors_outlined, Icons.sensors, l.navDevices),
      (Icons.notifications_outlined, Icons.notifications, l.navAlerts),
      (Icons.settings_outlined, Icons.settings, l.navSettings),
    ];

    void select(int i) =>
        shell.goBranch(i, initialLocation: i == shell.currentIndex);

    final wide = MediaQuery.sizeOf(context).width >= Breakpoints.medium;
    if (!wide) {
      return Scaffold(
        body: shell,
        bottomNavigationBar: NavigationBar(
          selectedIndex: shell.currentIndex,
          onDestinationSelected: select,
          destinations: [
            for (final (i, d) in destinations.indexed)
              NavigationDestination(
                icon: i == 2 ? alertIcon(d.$1) : Icon(d.$1),
                selectedIcon: i == 2 ? alertIcon(d.$2) : Icon(d.$2),
                label: d.$3,
              ),
          ],
        ),
      );
    }
    return Scaffold(
      body: Row(
        children: [
          NavigationRail(
            selectedIndex: shell.currentIndex,
            onDestinationSelected: select,
            labelType: NavigationRailLabelType.all,
            destinations: [
              for (final (i, d) in destinations.indexed)
                NavigationRailDestination(
                  icon: i == 2 ? alertIcon(d.$1) : Icon(d.$1),
                  selectedIcon: i == 2 ? alertIcon(d.$2) : Icon(d.$2),
                  label: Text(d.$3),
                ),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(child: shell),
        ],
      ),
    );
  }
}
