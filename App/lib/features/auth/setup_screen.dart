import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import 'auth_widgets.dart';

/// First start of a gateway: the setup code from the api's log, the installation and the owner.
class SetupScreen extends ConsumerStatefulWidget {
  const SetupScreen({super.key});

  @override
  ConsumerState<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends ConsumerState<SetupScreen> {
  final _code = TextEditingController();
  final _name = TextEditingController(text: 'Home');
  final _timezone = TextEditingController(text: _guessTimezone());
  final _user = TextEditingController();
  final _display = TextEditingController();
  final _password = TextEditingController();
  Object? _error;
  var _busy = false;

  static String _guessTimezone() {
    final name = DateTime.now().timeZoneName;
    return name.contains('/') ? name : 'Europe/Berlin';
  }

  @override
  void dispose() {
    for (final c in [_code, _name, _timezone, _user, _display, _password]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final session = await ref.read(repositoryProvider).setup(
        setupCode: _code.text,
        name: _name.text.trim(),
        timezone: _timezone.text.trim(),
        username: _user.text.trim(),
        password: _password.text,
        displayName: _display.text.trim(),
      );
      await ref.read(sessionProvider.notifier).signIn(session);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final hubOnline = ref.watch(metaProvider).value?.hubOnline ?? true;
    return AuthScaffold(
      title: l.setupTitle,
      subtitle: l.setupSubtitle,
      children: [
        authField(context, controller: _code, label: l.setupCode, helper: l.setupCodeHint,
            capitalization: TextCapitalization.characters),
        authField(context, controller: _name, label: l.installationName),
        authField(context, controller: _timezone, label: l.timezone, helper: l.timezoneHint),
        authField(context, controller: _user, label: l.username),
        authField(context, controller: _display, label: l.displayName),
        authField(context, controller: _password, label: l.password, obscure: true, helper: l.passwordHint,
            action: TextInputAction.done, onSubmitted: (_) => _submit()),
        if (!hubOnline)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(l.setupNeedsHub, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        FormError(_error),
        FilledButton(onPressed: _busy ? null : _submit, child: Text(l.setupCreate)),
      ],
    );
  }
}
