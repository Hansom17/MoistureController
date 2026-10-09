import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import 'auth_widgets.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _user = TextEditingController();
  final _password = TextEditingController();
  final _device = TextEditingController(text: defaultDeviceName());
  Object? _error;
  var _busy = false;

  @override
  void dispose() {
    _user.dispose();
    _password.dispose();
    _device.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final session = await ref.read(repositoryProvider).login(
        username: _user.text.trim(),
        password: _password.text,
        deviceName: _device.text.trim(),
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
    final name = ref.watch(metaProvider).value?.name ?? '';
    return AuthScaffold(
      title: name.isEmpty ? l.appTitle : name,
      subtitle: l.loginSubtitle,
      children: [
        authField(context, controller: _user, label: l.username),
        authField(context, controller: _password, label: l.password, obscure: true, action: TextInputAction.next),
        authField(context, controller: _device, label: l.thisDeviceName, helper: l.thisDeviceHint,
            action: TextInputAction.done, onSubmitted: (_) => _submit()),
        FormError(_error),
        FilledButton(onPressed: _busy ? null : _submit, child: Text(l.signIn)),
      ],
    );
  }
}
