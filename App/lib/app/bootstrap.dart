import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/api_endpoint.dart';
import '../core/session.dart';
import '../data/repositories/moisture_repository.dart';
import 'app.dart';

/// Shared start-up for all flavors.
///
/// [connection] is set by the mobile flavor (LAN discovery, App/specs.md Part A §6.4);
/// [onUnreachable] lets its repository report "server not reachable" so the
/// app searches again instead of failing.
Future<void> bootstrap(
  MoistureRepository repository, {
  ApiConnection? connection,
  void Function(void Function() callback)? onUnreachable,
  void Function(void Function() callback)? onUnauthorized,
  String origin = 'http://moisture.local',
}) async {
  WidgetsFlutterBinding.ensureInitialized();
  _installErrorHandlers();
  final prefs = await SharedPreferences.getInstance();
  final container = ProviderContainer(
    overrides: [
      repositoryProvider.overrideWithValue(repository),
      sharedPreferencesProvider.overrideWithValue(prefs),
      originProvider.overrideWithValue(origin),
      if (connection != null)
        apiConnectionProvider.overrideWithValue(connection),
    ],
  );
  onUnreachable?.call(
    () => container.read(apiEndpointProvider.notifier).reportUnreachable(),
  );
  onUnauthorized?.call(() => container.read(sessionProvider.notifier).expired());
  runApp(
    UncontrolledProviderScope(container: container, child: const MoistureApp()),
  );
}

/// Unexpected errors are logged, not fatal; a broken widget shows a small
/// card instead of a red screen (App/specs.md Part A §6.4.1).
void _installErrorHandlers() {
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    debugPrint('Unhandled error: $error\n$stack');
    return true;
  };
}
