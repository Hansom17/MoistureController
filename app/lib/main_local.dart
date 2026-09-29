import 'app/bootstrap.dart';
import 'data/repositories/api_moisture_repository.dart';

/// Against a local backend (server/docker-compose.yml in dev auth mode):
///
///   flutter run -d chrome --web-port 8420 -t lib/main_local.dart
///   flutter run -t lib/main_local.dart --dart-define=API_URL=http://192.168.1.10:8000
///
/// Signs in as `DEV_UID` with an unsigned dev token — only accepted by a
/// backend running with MC_AUTH_MODE=dev. Firebase login replaces this (M6).
void main() {
  const apiUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://localhost:8000',
  );
  const uid = String.fromEnvironment('DEV_UID', defaultValue: 'dev-user');
  bootstrap(
    ApiMoistureRepository(baseUrl: apiUrl, token: () async => 'dev:$uid'),
  );
}
