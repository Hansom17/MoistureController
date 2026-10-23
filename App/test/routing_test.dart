import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/app/router.dart';
import 'package:moisture_controller/data/models.dart';

AsyncValue<GatewayMeta> meta({bool setup = false}) =>
    AsyncData(GatewayMeta(name: 'Home', setupRequired: setup, hubOnline: true));

AsyncValue<AppUser?> user([bool signedIn = true]) => AsyncData(
  signedIn ? const AppUser(id: 'u', username: 'u', displayName: 'U', role: Role.member) : null,
);

void main() {
  group('authRedirect', () {
    String? go(String location, {AsyncValue<GatewayMeta>? m, AsyncValue<AppUser?>? s}) =>
        authRedirect(location: location, meta: m ?? meta(), session: s ?? user());

    test('while loading or failing, everything waits on /start', () {
      expect(go('/plants', m: const AsyncLoading()), '/start');
      expect(go('/plants', s: const AsyncLoading()), '/start');
      expect(go('/plants', m: AsyncError('x', StackTrace.empty)), '/start');
      expect(go('/start', m: const AsyncLoading()), isNull);
    });

    test('a gateway that is not set up leads to /setup', () {
      expect(go('/plants', m: meta(setup: true), s: user(false)), '/setup');
      expect(go('/login', m: meta(setup: true), s: user(false)), '/setup');
      expect(go('/setup', m: meta(setup: true), s: user(false)), isNull);
    });

    test('nobody signed in leads to /login', () {
      expect(go('/plants', s: user(false)), '/login');
      expect(go('/settings/users', s: user(false)), '/login');
      expect(go('/login', s: user(false)), isNull);
    });

    test('signed in users leave the entry screens', () {
      expect(go('/start'), '/plants');
      expect(go('/login'), '/plants');
      expect(go('/setup'), '/plants');
      expect(go('/devices'), isNull);
    });

    test('invite links work in every state', () {
      expect(go('/join', s: user(false)), isNull);
      expect(go('/join', m: meta(setup: true), s: user(false)), isNull);
      expect(go('/join', m: const AsyncLoading()), isNull);
    });
  });

  group('initialLocation', () {
    test('the invite code in the fragment becomes a query parameter', () {
      expect(initialLocation(Uri.parse('http://gw/join#c=ABC123')), '/join?code=ABC123');
      expect(initialLocation(Uri.parse('http://gw/join/#c=ABC123')), '/join?code=ABC123');
      expect(initialLocation(Uri.parse('http://gw/join?code=XYZ')), '/join?code=XYZ');
    });

    test('everything else starts at /start', () {
      expect(initialLocation(Uri.parse('http://gw/')), '/start');
      expect(initialLocation(Uri.parse('http://gw/plants/p1')), '/start');
    });
  });
}
