import 'dart:async';

import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Finding the API server on the local network (App/specs.md Part A §6.4).
///
/// Pure Dart: the mDNS browse, the health probe and the storage are injected,
/// so the resolution order is unit-tested without a network.

/// A server answering `GET /healthz` as a Moisture API.
class ApiServer {
  const ApiServer({required this.url, required this.name, this.id, this.auth});

  final Uri url;
  final String name;

  /// Stable installation id (`MC_INSTANCE_ID`); survives IP changes.
  final String? id;

  /// `dev` (unsigned tokens, local stack) or `firebase`.
  final String? auth;

  String get address => url.hasPort ? '${url.host}:${url.port}' : url.host;

  @override
  bool operator ==(Object other) =>
      other is ApiServer && other.url == url && other.id == id;

  @override
  int get hashCode => Object.hash(url, id);
}

/// An unverified mDNS result: where a server claims to be.
class MdnsCandidate {
  const MdnsCandidate({required this.url, required this.name});

  final Uri url;
  final String name;
}

/// Browses `_moisture-api._tcp` for [timeout].
abstract class MdnsSource {
  Future<List<MdnsCandidate>> browse(Duration timeout);
}

/// What a server answers to the health probe.
class ApiHealth {
  const ApiHealth({this.id, this.auth});

  final String? id;
  final String? auth;
}

abstract class ApiProber {
  /// Null when nothing answers there, or what answers is not a Moisture API.
  Future<ApiHealth?> probe(Uri base, {Duration timeout});
}

class DioApiProber implements ApiProber {
  DioApiProber({HttpClientAdapter? adapter}) : _adapter = adapter;

  final HttpClientAdapter? _adapter;

  @override
  Future<ApiHealth?> probe(
    Uri base, {
    Duration timeout = const Duration(milliseconds: 1500),
  }) async {
    final dio = Dio(
      BaseOptions(
        connectTimeout: timeout,
        receiveTimeout: timeout,
        sendTimeout: timeout,
      ),
    );
    if (_adapter != null) dio.httpClientAdapter = _adapter;
    try {
      final response = await dio.getUri<dynamic>(base.resolve('/healthz'));
      final data = response.data;
      if (data is Map && data['service'] == 'moisture-api') {
        return ApiHealth(
          id: data['id'] as String?,
          auth: data['auth'] as String?,
        );
      }
      return null;
    } on DioException {
      return null;
    } finally {
      dio.close(force: true);
    }
  }
}

/// The server used last, kept across app starts (prefs only, no secrets).
abstract class ApiEndpointStore {
  ({Uri url, String? id})? read();
  Future<void> write(ApiServer server);
}

class PrefsApiEndpointStore implements ApiEndpointStore {
  PrefsApiEndpointStore(this._prefs);

  final SharedPreferences _prefs;

  static const _urlKey = 'api_url';
  static const _idKey = 'api_id';

  @override
  ({Uri url, String? id})? read() {
    final url = _prefs.getString(_urlKey);
    final uri = url == null ? null : Uri.tryParse(url);
    if (uri == null || !uri.hasAuthority) return null;
    return (url: uri, id: _prefs.getString(_idKey));
  }

  @override
  Future<void> write(ApiServer server) async {
    await _prefs.setString(_urlKey, server.url.toString());
    if (server.id != null) {
      await _prefs.setString(_idKey, server.id!);
    } else {
      await _prefs.remove(_idKey);
    }
  }
}

sealed class DiscoveryResult {
  const DiscoveryResult();
}

class DiscoveryFound extends DiscoveryResult {
  const DiscoveryFound(this.server);
  final ApiServer server;
}

class DiscoveryChoose extends DiscoveryResult {
  const DiscoveryChoose(this.servers);
  final List<ApiServer> servers;
}

class DiscoveryNone extends DiscoveryResult {
  const DiscoveryNone();
}

class ApiDiscovery {
  ApiDiscovery({
    required this.mdns,
    required this.prober,
    required this.store,
    this.seed,
    this.browseTimeout = const Duration(seconds: 5),
  });

  final MdnsSource mdns;
  final ApiProber prober;
  final ApiEndpointStore store;

  /// Address to try when nothing is remembered yet (`API_URL`, App/specs.md Part A §14).
  final Uri? seed;
  final Duration browseTimeout;

  /// App/specs.md Part A §6.4 resolution order: last used address, then mDNS.
  Future<DiscoveryResult> resolve() async {
    final remembered = store.read();
    final first = remembered?.url ?? seed;
    if (first != null) {
      final health = await prober.probe(first);
      // A different id at the remembered address is another installation.
      if (health != null &&
          (remembered?.id == null || remembered!.id == health.id)) {
        return DiscoveryFound(_server(first, null, health));
      }
    }

    final candidates = await mdns.browse(browseTimeout);
    final verified = (await Future.wait([
      for (final c in candidates) _verify(c),
    ])).whereType<ApiServer>().toList();

    if (verified.isEmpty) return const DiscoveryNone();
    final known = remembered?.id;
    if (known != null) {
      final match = verified.where((s) => s.id == known);
      if (match.isNotEmpty) return DiscoveryFound(match.first);
    }
    if (verified.length == 1) return DiscoveryFound(verified.single);
    verified.sort((a, b) => a.name.compareTo(b.name));
    return DiscoveryChoose(verified);
  }

  /// Verifies a hand-typed address; null when no Moisture API answers there.
  Future<ApiServer?> check(Uri url) async {
    final health = await prober.probe(url, timeout: const Duration(seconds: 4));
    return health == null ? null : _server(url, null, health);
  }

  Future<void> remember(ApiServer server) => store.write(server);

  Future<ApiServer?> _verify(MdnsCandidate c) async {
    final health = await prober.probe(c.url);
    return health == null ? null : _server(c.url, c.name, health);
  }

  static ApiServer _server(Uri url, String? name, ApiHealth health) =>
      ApiServer(
        url: url,
        name: name ?? (url.hasPort ? '${url.host}:${url.port}' : url.host),
        id: health.id,
        auth: health.auth,
      );
}

/// `host`, `host:port` or a full URL → base URI. A missing port means 8000
/// (the API's default); a missing scheme means http (local flavor only).
Uri? parseServerAddress(String input) {
  var text = input.trim();
  if (text.isEmpty) return null;
  if (!text.contains('://')) text = 'http://$text';
  final uri = Uri.tryParse(text);
  if (uri == null || uri.host.isEmpty) return null;
  final port = uri.hasPort ? uri.port : (uri.scheme == 'https' ? 443 : 8000);
  return Uri(scheme: uri.scheme, host: uri.host, port: port);
}

/// Plain HTTP is only acceptable towards this machine or the home network
/// (App/specs.md Part A §6.4.3): loopback, private IPv4 ranges, link-local, `.local`.
bool isLocalNetworkHost(String host) {
  final h = host.toLowerCase();
  if (h == 'localhost' || h.endsWith('.local') || h.endsWith('.localhost')) {
    return true;
  }
  final m = RegExp(r'^(\d+)\.(\d+)\.\d+\.\d+$').firstMatch(h);
  if (m == null) return h == '::1';
  final a = int.parse(m[1]!);
  final b = int.parse(m[2]!);
  return a == 10 ||
      a == 127 ||
      (a == 192 && b == 168) ||
      (a == 172 && b >= 16 && b <= 31) ||
      (a == 169 && b == 254);
}
