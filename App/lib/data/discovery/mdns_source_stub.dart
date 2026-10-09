import 'api_discovery.dart';

MdnsSource createMdnsSource() => _NoMdns();

class _NoMdns implements MdnsSource {
  @override
  Future<List<MdnsCandidate>> browse(Duration timeout) async => const [];
}
