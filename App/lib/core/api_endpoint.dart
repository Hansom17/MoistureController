import 'dart:async';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/discovery/api_discovery.dart';
import 'app_data.dart';
import 'session.dart';

/// Where the API is and whether we can reach it (App/specs.md Part A §6.4.1).
sealed class ApiEndpointState {
  const ApiEndpointState();
}

/// Flavors with a fixed API address (dev, prod, fake): nothing to find.
class ApiFixed extends ApiEndpointState {
  const ApiFixed();
}

class ApiSearching extends ApiEndpointState {
  const ApiSearching();
}

class ApiConnected extends ApiEndpointState {
  const ApiConnected(this.server);
  final ApiServer server;
}

class ApiUnreachable extends ApiEndpointState {
  const ApiUnreachable({this.last});
  final Uri? last;
}

class ApiChoose extends ApiEndpointState {
  const ApiChoose(this.servers);
  final List<ApiServer> servers;
}

/// What the mobile flavor wires in: discovery, and how to point the
/// repository at a new address. Null on web and in the fake flavor.
class ApiConnection {
  const ApiConnection({required this.discovery, required this.apply});

  final ApiDiscovery discovery;
  final void Function(Uri baseUrl) apply;
}

final apiConnectionProvider = Provider<ApiConnection?>((ref) => null);

final apiEndpointProvider =
    NotifierProvider<ApiEndpointController, ApiEndpointState>(
      ApiEndpointController.new,
    );

class ApiEndpointController extends Notifier<ApiEndpointState> {
  Timer? _retry;
  var _attempt = 0;
  var _searching = false;
  var _disposed = false;
  Uri? _last;

  ApiConnection? get _connection => ref.read(apiConnectionProvider);

  @override
  ApiEndpointState build() {
    _disposed = false;
    ref.onDispose(() {
      _disposed = true;
      _retry?.cancel();
    });
    if (ref.watch(apiConnectionProvider) == null) return const ApiFixed();
    Future.microtask(search);
    return const ApiSearching();
  }

  /// Runs the resolution order; on failure keeps searching in the background
  /// with backoff 2 s → 30 s (App/specs.md Part A §6.4).
  Future<void> search() async {
    final connection = _connection;
    if (connection == null || _searching) return;
    _searching = true;
    _retry?.cancel();
    if (state is! ApiSearching) state = const ApiSearching();
    try {
      final result = await connection.discovery.resolve();
      if (_disposed) return;
      switch (result) {
        case DiscoveryFound(:final server):
          await _connect(server);
        case DiscoveryChoose(:final servers):
          _attempt = 0;
          state = ApiChoose(servers);
        case DiscoveryNone():
          _unreachable();
      }
    } on Object {
      if (!_disposed) _unreachable();
    } finally {
      _searching = false;
    }
  }

  void _unreachable() {
    state = ApiUnreachable(last: _last);
    final delay = Duration(seconds: min(30, 2 << _attempt++));
    _retry = Timer(delay, search);
  }

  Future<void> _connect(ApiServer server) async {
    final previous = state;
    final changed = previous is! ApiConnected || previous.server != server;
    _attempt = 0;
    _last = server.url;
    await _connection!.discovery.remember(server);
    _connection!.apply(server.url);
    state = ApiConnected(server);
    if (changed) _refreshData();
  }

  /// Data loaded (or failed) against the old address is stale now.
  void _refreshData() {
    ref.invalidate(metaProvider);
    ref.invalidate(plantsProvider);
    ref.invalidate(readingsProvider);
    ref.invalidate(commandsProvider);
    ref.invalidate(rulesProvider);
    ref.invalidate(devicesProvider);
    ref.invalidate(alertsProvider);
    ref.invalidate(gatewayStatusProvider);
  }

  /// The user picked one of several found servers.
  Future<void> select(ApiServer server) => _connect(server);

  /// A hand-typed address. Null on success, otherwise why not.
  Future<ManualAddressError?> setManual(String input) async {
    final connection = _connection;
    final uri = parseServerAddress(input);
    if (connection == null || uri == null) return ManualAddressError.invalid;
    if (uri.scheme == 'http' && !isLocalNetworkHost(uri.host)) {
      return ManualAddressError.notLocal;
    }
    final server = await connection.discovery.check(uri);
    if (server == null) return ManualAddressError.noAnswer;
    await _connect(server);
    return null;
  }

  /// The repository's request failed at the network level.
  void reportUnreachable() {
    if (state is ApiConnected) search();
  }
}

enum ManualAddressError { invalid, notLocal, noAnswer }
