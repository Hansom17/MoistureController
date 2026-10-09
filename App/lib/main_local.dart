import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app/bootstrap.dart';
import 'core/api_endpoint.dart';
import 'data/discovery/api_discovery.dart';
import 'data/discovery/mdns_source.dart';
import 'data/repositories/api_moisture_repository.dart';

/// Against a local backend (api/docker-compose.yml in dev auth mode). The app
/// finds the server on the network itself (App/specs.md Part A §6.4); the server
/// advertises via `api/scripts/advertise_mdns.py`.
///
///   flutter run -d chrome --web-port 8420 -t lib/main_local.dart
///   flutter run -t lib/main_local.dart
///
/// `API_URL` is only the first address to try when none is remembered yet
/// (the web build can't use mDNS and relies on it).
///
/// Signs in as `DEV_UID` with an unsigned dev token — only accepted by a
/// backend running with MC_AUTH_MODE=dev. Firebase login replaces this (M6).
void main() async {
  const seed = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://localhost:8000',
  );
  const uid = String.fromEnvironment('DEV_UID', defaultValue: 'dev-user');
  WidgetsFlutterBinding.ensureInitialized(); // before the first platform channel call
  final prefs = await SharedPreferences.getInstance();
  final seedUrl = parseServerAddress(seed)!;
  final repository = ApiMoistureRepository(
    baseUrl: seedUrl.toString(),
    token: () async => 'dev:$uid',
  );
  final discovery = ApiDiscovery(
    mdns: createMdnsSource(),
    prober: DioApiProber(),
    store: PrefsApiEndpointStore(prefs),
    seed: seedUrl,
  );
  bootstrap(
    repository,
    connection: ApiConnection(
      discovery: discovery,
      apply: repository.setBaseUrl,
    ),
    onUnreachable: (callback) => repository.onUnreachable = callback,
  );
}
