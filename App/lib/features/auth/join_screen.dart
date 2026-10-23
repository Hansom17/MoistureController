import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/session.dart';
import '../../data/models.dart';
import 'auth_widgets.dart';

/// Invite link `/join#c=<code>`: preview the invite, choose a username and password (App/specs.md Part A §12).
class JoinScreen extends ConsumerStatefulWidget {
  const JoinScreen({super.key, required this.code});

  final String? code;

  @override
  ConsumerState<JoinScreen> createState() => _JoinScreenState();
}

class _JoinScreenState extends ConsumerState<JoinScreen> {
  final _user = TextEditingController();
  final _display = TextEditingController();
  final _password = TextEditingController();
  final _device = TextEditingController(text: defaultDeviceName());
  Future<InvitePreview>? _preview;
  Object? _error;
  var _busy = false;

  @override
  void initState() {
    super.initState();
    final code = widget.code;
    if (code != null && code.isNotEmpty) _preview = ref.read(repositoryProvider).previewInvite(code);
  }

  @override
  void dispose() {
    for (final c in [_user, _display, _password, _device]) {
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
      final session = await ref.read(repositoryProvider).acceptInvite(
        code: widget.code!,
        username: _user.text.trim(),
        password: _password.text,
        displayName: _display.text.trim(),
        deviceName: _device.text.trim(),
      );
      await ref.read(sessionProvider.notifier).signIn(session);
      if (mounted) context.go('/plants'); // /join stays open without a login, so leave it explicitly
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final future = _preview;
    if (future == null) {
      return AuthScaffold(title: l.joinTitle, children: [Text(l.errorInvalidInvite, textAlign: TextAlign.center)]);
    }
    return FutureBuilder<InvitePreview>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(body: Center(child: CircularProgressIndicator()));
        }
        if (snapshot.hasError) {
          return AuthScaffold(title: l.joinTitle, children: [FormError(snapshot.error)]);
        }
        final p = snapshot.requireData;
        return AuthScaffold(
          title: l.joinInstallation(p.installation),
          subtitle: l.joinRole(roleLabel(l, p.role)),
          children: [
            authField(context, controller: _user, label: l.username),
            authField(context, controller: _display, label: l.displayName),
            authField(context, controller: _password, label: l.password, obscure: true, helper: l.passwordHint),
            authField(context, controller: _device, label: l.thisDeviceName, action: TextInputAction.done,
                onSubmitted: (_) => _submit()),
            FormError(_error),
            FilledButton(onPressed: _busy ? null : _submit, child: Text(l.joinAccept)),
          ],
        );
      },
    );
  }
}
