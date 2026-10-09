import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/api_problem.dart';
import '../data/models.dart';
import '../data/repositories/moisture_repository.dart';

/// Overridden in `main_*.dart` with the flavor's repository.
final repositoryProvider = Provider<MoistureRepository>(
  (ref) => throw UnimplementedError('repositoryProvider must be overridden'),
);

/// Overridden in `main_*.dart` with the loaded instance.
final sharedPreferencesProvider = Provider<SharedPreferences>(
  (ref) =>
      throw UnimplementedError('sharedPreferencesProvider must be overridden'),
);

/// The address pages and invite links are served from; overridden by the flavor. On web: the page's origin.
final originProvider = Provider<String>((ref) => 'http://moisture.local');

/// `GET /meta`: is this gateway set up, is the hub reachable (App/specs.md Part A §5).
final metaProvider = FutureProvider<GatewayMeta>(
  (ref) => ref.watch(repositoryProvider).meta(),
);

const _tokenKey = 'token';

/// Who is signed in. `null` = nobody. The token lives in the browser's storage (App/specs.md Part A §2).
final sessionProvider = AsyncNotifierProvider<SessionController, AppUser?>(
  SessionController.new,
);

class SessionController extends AsyncNotifier<AppUser?> {
  @override
  Future<AppUser?> build() async {
    final prefs = ref.watch(sharedPreferencesProvider);
    final repo = ref.watch(repositoryProvider);
    final token = prefs.getString(_tokenKey);
    if (token == null) return null;
    repo.useToken(token);
    try {
      return await repo.me();
    } on ApiProblem catch (e) {
      // A token the api no longer knows ends the session; a network error leaves it for a retry.
      if (e.type == ApiProblem.unauthorized) {
        await _forget();
        return null;
      }
      rethrow;
    }
  }

  Future<void> _forget() async {
    ref.read(repositoryProvider).useToken(null);
    await ref.read(sharedPreferencesProvider).remove(_tokenKey);
  }

  /// After setup, login or accepting an invite.
  Future<void> signIn(Session session) async {
    ref.read(repositoryProvider).useToken(session.token);
    await ref.read(sharedPreferencesProvider).setString(_tokenKey, session.token);
    ref.invalidate(metaProvider);
    state = AsyncData(session.user);
  }

  Future<void> signOut() async {
    try {
      await ref.read(repositoryProvider).logout();
    } on Object {
      // sign out locally even when the gateway cannot be reached
    }
    await _forget();
    state = const AsyncData(null);
  }

  /// The api rejected the token (401): back to the login screen.
  Future<void> expired() async {
    await _forget();
    state = const AsyncData(null);
  }

  /// The role or name changed (an `installation` event, a role change by an admin).
  Future<void> refresh() async {
    try {
      final user = await ref.read(repositoryProvider).me();
      state = AsyncData(user);
    } on ApiProblem catch (e) {
      if (e.type == ApiProblem.unauthorized) await expired();
    }
  }
}

/// The signed-in user (null while loading or signed out).
final currentUserProvider = Provider<AppUser?>(
  (ref) => ref.watch(sessionProvider).value,
);

/// The signed-in user's role; the least privileged one while nobody is known yet.
final currentUserProviderRole = Provider<Role>(
  (ref) => ref.watch(currentUserProvider)?.role ?? Role.viewer,
);
