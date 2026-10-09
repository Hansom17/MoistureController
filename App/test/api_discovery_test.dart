import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/core/api_endpoint.dart';
import 'package:moisture_controller/data/discovery/api_discovery.dart';

class FakeMdns implements MdnsSource {
  FakeMdns(this.candidates);
  List<MdnsCandidate> candidates;
  var browses = 0;

  @override
  Future<List<MdnsCandidate>> browse(Duration timeout) async {
    browses++;
    return candidates;
  }
}

/// Answers per URL; anything else does not answer.
class FakeProber implements ApiProber {
  FakeProber(this.alive);
  Map<String, ApiHealth> alive;
  final probed = <String>[];

  @override
  Future<ApiHealth?> probe(
    Uri base, {
    Duration timeout = const Duration(seconds: 1),
  }) async {
    probed.add(base.toString());
    return alive[base.toString()];
  }
}

class MemoryStore implements ApiEndpointStore {
  ({Uri url, String? id})? value;

  @override
  ({Uri url, String? id})? read() => value;

  @override
  Future<void> write(ApiServer server) async =>
      value = (url: server.url, id: server.id);
}

MdnsCandidate cand(String host, [String name = 'Moisture API']) =>
    MdnsCandidate(url: Uri.parse('http://$host:8000'), name: name);

ApiDiscovery discovery(
  FakeMdns mdns,
  FakeProber prober,
  MemoryStore store, {
  Uri? seed,
}) => ApiDiscovery(
  mdns: mdns,
  prober: prober,
  store: store,
  seed: seed,
  browseTimeout: Duration.zero,
);

void main() {
  group('ApiDiscovery.resolve', () {
    test('a reachable remembered address wins without scanning', () async {
      final mdns = FakeMdns([cand('10.0.0.9')]);
      final store = MemoryStore()
        ..value = (url: Uri.parse('http://10.0.0.5:8000'), id: 'a');
      final d = discovery(
        mdns,
        FakeProber({'http://10.0.0.5:8000': const ApiHealth(id: 'a')}),
        store,
      );
      final r = await d.resolve() as DiscoveryFound;
      expect(r.server.url.host, '10.0.0.5');
      expect(mdns.browses, 0);
    });

    test('the same installation is found again after its IP changed', () async {
      final store = MemoryStore()
        ..value = (url: Uri.parse('http://10.0.0.5:8000'), id: 'a');
      final d = discovery(
        FakeMdns([cand('10.0.0.7', 'Pi'), cand('10.0.0.8', 'Other')]),
        FakeProber({
          'http://10.0.0.7:8000': const ApiHealth(id: 'other'),
          'http://10.0.0.8:8000': const ApiHealth(id: 'a'),
        }),
        store,
      );
      final r = await d.resolve() as DiscoveryFound;
      expect(r.server.url.host, '10.0.0.8');
    });

    test(
      'another installation at the remembered address is not used',
      () async {
        final store = MemoryStore()
          ..value = (url: Uri.parse('http://10.0.0.5:8000'), id: 'a');
        final d = discovery(
          FakeMdns([]),
          FakeProber({'http://10.0.0.5:8000': const ApiHealth(id: 'stranger')}),
          store,
        );
        expect(await d.resolve(), isA<DiscoveryNone>());
      },
    );

    test('the seed address is tried when nothing is remembered', () async {
      final d = discovery(
        FakeMdns([]),
        FakeProber({'http://localhost:8000': const ApiHealth(id: 'x')}),
        MemoryStore(),
        seed: Uri.parse('http://localhost:8000'),
      );
      expect(await d.resolve(), isA<DiscoveryFound>());
    });

    test('one verified result is used, unverified ones are dropped', () async {
      final d = discovery(
        FakeMdns([cand('10.0.0.7'), cand('10.0.0.99')]),
        FakeProber({'http://10.0.0.7:8000': const ApiHealth(id: 'a')}),
        MemoryStore(),
      );
      final r = await d.resolve() as DiscoveryFound;
      expect(r.server.url.host, '10.0.0.7');
    });

    test('several servers become a choice, sorted by name', () async {
      final d = discovery(
        FakeMdns([cand('10.0.0.7', 'Zed'), cand('10.0.0.8', 'Abe')]),
        FakeProber({
          'http://10.0.0.7:8000': const ApiHealth(id: 'z'),
          'http://10.0.0.8:8000': const ApiHealth(id: 'a'),
        }),
        MemoryStore(),
      );
      final r = await d.resolve() as DiscoveryChoose;
      expect(r.servers.map((s) => s.name), ['Abe', 'Zed']);
    });

    test('nothing found', () async {
      final d = discovery(FakeMdns([]), FakeProber({}), MemoryStore());
      expect(await d.resolve(), isA<DiscoveryNone>());
    });
  });

  group('addresses', () {
    test('parseServerAddress', () {
      expect(
        parseServerAddress('192.168.1.10')!.toString(),
        'http://192.168.1.10:8000',
      );
      expect(parseServerAddress('pi.local:9000')!.port, 9000);
      expect(parseServerAddress('https://api.example.com')!.port, 443);
      expect(parseServerAddress('  '), isNull);
    });

    test('isLocalNetworkHost', () {
      for (final h in [
        'localhost',
        '192.168.1.5',
        '10.1.2.3',
        '172.16.0.1',
        'pi.local',
        '169.254.1.1',
      ]) {
        expect(isLocalNetworkHost(h), isTrue, reason: h);
      }
      for (final h in ['8.8.8.8', '172.32.0.1', 'example.com']) {
        expect(isLocalNetworkHost(h), isFalse, reason: h);
      }
    });
  });

  group('ApiEndpointController', () {
    late FakeMdns mdns;
    late FakeProber prober;
    late MemoryStore store;
    late List<Uri> applied;
    late ProviderContainer container;

    ProviderContainer make({Uri? seed}) {
      applied = [];
      container = ProviderContainer(
        overrides: [
          apiConnectionProvider.overrideWithValue(
            ApiConnection(
              discovery: discovery(mdns, prober, store, seed: seed),
              apply: applied.add,
            ),
          ),
        ],
      );
      addTearDown(container.dispose);
      return container;
    }

    // Waits until the controller left `searching` (or fails after 2 s).
    Future<void> settle() async {
      for (var i = 0; i < 200; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
        if (container.read(apiEndpointProvider) is! ApiSearching) return;
      }
    }

    setUp(() {
      mdns = FakeMdns([]);
      prober = FakeProber({});
      store = MemoryStore();
    });

    test('no connection configured: fixed address, nothing to find', () {
      final c = ProviderContainer();
      addTearDown(c.dispose);
      expect(c.read(apiEndpointProvider), isA<ApiFixed>());
    });

    test('server absent at start is a state, not an exception', () async {
      final c = make();
      expect(c.read(apiEndpointProvider), isA<ApiSearching>());
      await settle();
      expect(c.read(apiEndpointProvider), isA<ApiUnreachable>());
      expect(applied, isEmpty);
    });

    test('finds the server, applies and remembers it', () async {
      mdns.candidates = [cand('10.0.0.7')];
      prober.alive = {
        'http://10.0.0.7:8000': const ApiHealth(id: 'a', auth: 'dev'),
      };
      final c = make();
      await settle();
      final s = c.read(apiEndpointProvider) as ApiConnected;
      expect(s.server.auth, 'dev');
      expect(applied.single.host, '10.0.0.7');
      expect(store.value!.id, 'a');
    });

    test(
      'a connection failure triggers a new search and recovers at a new IP',
      () async {
        mdns.candidates = [cand('10.0.0.7')];
        prober.alive = {'http://10.0.0.7:8000': const ApiHealth(id: 'a')};
        final c = make();
        await settle();
        expect(c.read(apiEndpointProvider), isA<ApiConnected>());

        // the server comes back under another address
        mdns.candidates = [cand('10.0.0.8')];
        prober.alive = {'http://10.0.0.8:8000': const ApiHealth(id: 'a')};
        c.read(apiEndpointProvider.notifier).reportUnreachable();
        await settle();
        expect(
          (c.read(apiEndpointProvider) as ApiConnected).server.url.host,
          '10.0.0.8',
        );
        expect(applied.last.host, '10.0.0.8');
      },
    );

    test('manual address: validated, local only, probed', () async {
      final c = make();
      await settle();
      final n = c.read(apiEndpointProvider.notifier);
      expect(await n.setManual('???'), ManualAddressError.invalid);
      expect(
        await n.setManual('http://8.8.8.8:8000'),
        ManualAddressError.notLocal,
      );
      expect(await n.setManual('10.0.0.3'), ManualAddressError.noAnswer);
      prober.alive = {'http://10.0.0.3:8000': const ApiHealth(id: 'm')};
      expect(await n.setManual('10.0.0.3'), isNull);
      expect(c.read(apiEndpointProvider), isA<ApiConnected>());
    });
  });
}
