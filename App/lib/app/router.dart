import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/app_data.dart';
import '../core/format.dart';
import '../core/live_updates.dart';
import '../core/session.dart';
import '../data/models.dart';
import '../features/alerts/alerts_screen.dart';
import '../features/auth/join_screen.dart';
import '../features/auth/login_screen.dart';
import '../features/auth/setup_screen.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/devices/add_device_screen.dart';
import '../features/devices/config_editor_screen.dart';
import '../features/devices/device_detail_screen.dart';
import '../features/devices/devices_screen.dart';
import '../features/gateway/gateway_screen.dart';
import '../features/installation/installation_screen.dart';
import '../features/plants/plant_detail_screen.dart';
import '../features/settings/data_screen.dart';
import '../features/settings/server_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/settings/tokens_screen.dart';
import '../features/users/users_screen.dart';
import '../ui/common.dart';
import 'theme/tokens.dart';

/// The invite link `/join#c=<code>` carries the code in the URL fragment, which the router never
/// sees (and which never reaches a server); map it to `/join?code=…` here (App/specs.md Part A §12).
String initialLocation(Uri url) {
  final path = url.path.endsWith('/') && url.path.length > 1
      ? url.path.substring(0, url.path.length - 1)
      : url.path;
  if (path.endsWith('/join') && url.fragment.startsWith('c=')) {
    return Uri(path: '/join', queryParameters: {'code': url.fragment.substring(2)}).toString();
  }
  if (path.endsWith('/join') && url.queryParameters['code'] != null) {
    return Uri(path: '/join', queryParameters: {'code': url.queryParameters['code']}).toString();
  }
  return '/start';
}

/// Where a visitor belongs, from the two things the app asks first: is the gateway set up, and who
/// is signed in (App/specs.md Part A §4, §5). `null` = stay.
String? authRedirect({
  required String location,
  required AsyncValue<GatewayMeta> meta,
  required AsyncValue<AppUser?> session,
}) {
  if (location == '/join') return null; // invite links work without a login
  if (meta.isLoading || session.isLoading || meta.hasError || session.hasError) {
    return location == '/start' ? null : '/start';
  }
  if (meta.requireValue.setupRequired) return location == '/setup' ? null : '/setup';
  if (session.requireValue == null) return location == '/login' ? null : '/login';
  if (location == '/start' || location == '/login' || location == '/setup') return '/plants';
  return null;
}

/// Lets the router re-run its redirect when the meta or session state changes.
class _AuthRefresh extends ChangeNotifier {
  void poke() => notifyListeners();
}

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = _AuthRefresh();
  ref.listen(metaProvider, (_, _) => refresh.poke());
  ref.listen(sessionProvider, (_, _) => refresh.poke());
  ref.onDispose(refresh.dispose);

  final router = GoRouter(
    initialLocation: initialLocation(Uri.base),
    refreshListenable: refresh,
    redirect: (context, state) => authRedirect(
      location: state.uri.path,
      meta: ref.read(metaProvider),
      session: ref.read(sessionProvider),
    ),
    routes: [
      GoRoute(path: '/start', builder: (_, _) => const _StartScreen()),
      GoRoute(path: '/setup', builder: (_, _) => const SetupScreen()),
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/join', builder: (_, state) => JoinScreen(code: state.uri.queryParameters['code'])),
      GoRoute(path: '/server', builder: (_, _) => const ServerScreen()),
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
                    builder: (_, state) => PlantDetailScreen(plantId: state.pathParameters['plantId']!),
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
                  GoRoute(path: 'add', builder: (_, _) => const AddDeviceScreen()),
                  GoRoute(
                    path: ':deviceId',
                    builder: (_, state) => DeviceDetailScreen(deviceId: state.pathParameters['deviceId']!),
                    routes: [
                      GoRoute(
                        path: 'config',
                        builder: (_, state) => ConfigEditorScreen(deviceId: state.pathParameters['deviceId']!),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/alerts', builder: (_, _) => const AlertsScreen())],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/settings',
                builder: (_, _) => const SettingsScreen(),
                routes: [
                  GoRoute(path: 'gateway', builder: (_, _) => const GatewayScreen()),
                  GoRoute(path: 'users', builder: (_, _) => const UsersScreen()),
                  GoRoute(path: 'tokens', builder: (_, _) => const TokensScreen()),
                  GoRoute(path: 'installation', builder: (_, _) => const InstallationScreen()),
                  GoRoute(path: 'data', builder: (_, _) => const DataScreen()),
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

/// Shown while the app finds out whether the gateway is set up and who is signed in.
class _StartScreen extends ConsumerWidget {
  const _StartScreen();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final meta = ref.watch(metaProvider);
    final session = ref.watch(sessionProvider);
    final error = meta.error ?? session.error;
    return Scaffold(
      body: error == null
          ? const Center(child: CircularProgressIndicator())
          : ErrorState(
              error: error,
              onRetry: () {
                ref.invalidate(metaProvider);
                ref.invalidate(sessionProvider);
              },
            ),
    );
  }
}

/// Bottom navigation on phones, navigation rail from 600 dp (App/specs.md Part A §9).
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.shell});

  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final openAlerts = ref.watch(openAlertCountProvider);
    ref.listen(notificationsProvider, (_, next) {
      final text = next.value;
      if (text != null) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
    });

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
