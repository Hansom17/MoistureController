import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_web_plugins/url_strategy.dart';

import 'app/bootstrap.dart';
import 'data/repositories/api_moisture_repository.dart';

/// The product: the app talks to the api it is served from (App/specs.md Part A §6.1).
///
///   flutter build web --release            # served by the gateway at `http://<gateway>/`
///   flutter run -d chrome --dart-define=API_URL=http://localhost:8000
///
/// The `API_URL` define is only for development against another host; on web the default is the page's own origin.
void main() {
  usePathUrlStrategy(); // links like /join#c=… and /plants/… instead of /#/plants/…
  WidgetsFlutterBinding.ensureInitialized();
  const configured = String.fromEnvironment('API_URL');
  final origin = configured.isNotEmpty
      ? configured.replaceAll(RegExp(r'/+$'), '')
      : kIsWeb
      ? Uri.base.origin
      : 'http://localhost:8000';
  final repository = ApiMoistureRepository(baseUrl: origin);
  bootstrap(
    repository,
    origin: origin,
    onUnreachable: (callback) => repository.onUnreachable = callback,
    onUnauthorized: (callback) => repository.onUnauthorized = callback,
  );
}
