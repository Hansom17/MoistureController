import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/session.dart';
import '../data/repositories/moisture_repository.dart';
import 'app.dart';

/// Shared start-up for all flavors.
Future<void> bootstrap(MoistureRepository repository) async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  runApp(
    ProviderScope(
      overrides: [
        repositoryProvider.overrideWithValue(repository),
        sharedPreferencesProvider.overrideWithValue(prefs),
      ],
      child: const MoistureApp(),
    ),
  );
}
