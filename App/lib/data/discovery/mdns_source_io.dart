import 'dart:async';
import 'dart:io';

import 'package:multicast_dns/multicast_dns.dart';

import 'api_discovery.dart';

const apiServiceType = '_moisture-api._tcp.local';

MdnsSource createMdnsSource() => _MulticastDnsSource();

/// id and auth mode are not read from the TXT record: the health probe that
/// verifies each result reports them authoritatively.
class _MulticastDnsSource implements MdnsSource {
  @override
  Future<List<MdnsCandidate>> browse(Duration timeout) async {
    final client = MDnsClient(
      // iOS/macOS need SO_REUSEPORT to share port 5353 with the system.
      rawDatagramSocketFactory:
          (
            dynamic host,
            int port, {
            bool reuseAddress = true,
            bool reusePort = false,
            int ttl = 1,
          }) => RawDatagramSocket.bind(
            host,
            port,
            reuseAddress: true,
            reusePort: !Platform.isAndroid,
            ttl: ttl,
          ),
    );
    final found = <String, MdnsCandidate>{};
    try {
      await client.start();
      await _collect(client, found).timeout(timeout, onTimeout: () {});
    } on Object {
      // No multicast permission / socket error: same as nothing found, the
      // user can still type an address.
    } finally {
      client.stop();
    }
    return found.values.toList();
  }

  Future<void> _collect(
    MDnsClient client,
    Map<String, MdnsCandidate> found,
  ) async {
    await for (final ptr in client.lookup<PtrResourceRecord>(
      ResourceRecordQuery.serverPointer(apiServiceType),
    )) {
      await for (final srv in client.lookup<SrvResourceRecord>(
        ResourceRecordQuery.service(ptr.domainName),
      )) {
        await for (final ip in client.lookup<IPAddressResourceRecord>(
          ResourceRecordQuery.addressIPv4(srv.target),
        )) {
          found[ptr.domainName] = MdnsCandidate(
            url: Uri(scheme: 'http', host: ip.address.address, port: srv.port),
            name: _instanceName(ptr.domainName),
          );
          break;
        }
      }
    }
  }

  /// `Moisture API (host)._moisture-api._tcp.local` → `Moisture API (host)`.
  static String _instanceName(String domain) {
    final i = domain.indexOf('._moisture-api');
    return i > 0 ? domain.substring(0, i) : domain;
  }
}
