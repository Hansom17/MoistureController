import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';

/// "My devices": the logins of this user, and the password (App/specs.md Part A §12).
class TokensScreen extends StatelessWidget {
  const TokensScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AppScope(
      builder: (context, user) => Scaffold(
        appBar: AppBar(title: Text(l.myDevices)),
        body: ListView(
          padding: const EdgeInsets.all(Spacing.lg),
          children: const [_TokensCard(), SizedBox(height: Spacing.md), _PasswordCard()],
        ),
      ),
    );
  }
}

class _TokensCard extends ConsumerWidget {
  const _TokensCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final tokens = ref.watch(tokensProvider);
    return SectionCard(
      title: l.myDevices,
      child: AsyncBody(
        value: tokens,
        onRetry: () => ref.invalidate(tokensProvider),
        data: (tokens) => Column(
          children: [
            for (final t in tokens)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.devices_outlined),
                title: Text(t.current ? '${t.name} · ${l.thisDevice}' : t.name),
                subtitle: Text(
                  t.lastUsedAt == null ? l.neverUsed : l.lastUsedAgo(formatAgo(l, t.lastUsedAt!)),
                ),
                trailing: t.current
                    ? null
                    : IconButton(
                        tooltip: l.revokeToken,
                        icon: const Icon(Icons.logout),
                        onPressed: () => ref.read(actionsProvider).revokeToken(t.id),
                      ),
              ),
          ],
        ),
      ),
    );
  }
}

class _PasswordCard extends ConsumerStatefulWidget {
  const _PasswordCard();

  @override
  ConsumerState<_PasswordCard> createState() => _PasswordCardState();
}

class _PasswordCardState extends ConsumerState<_PasswordCard> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  Object? _error;
  var _busy = false;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    super.dispose();
  }

  Future<void> _change() async {
    final l = context.l10n;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(repositoryProvider).changePassword(currentPassword: _current.text, newPassword: _next.text);
      if (!mounted) return;
      _current.clear();
      _next.clear();
      ref.invalidate(tokensProvider);
      showSnackBar(context, l.passwordChanged);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return SectionCard(
      title: l.changePassword,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(controller: _current, obscureText: true, decoration: InputDecoration(labelText: l.currentPassword)),
          const SizedBox(height: Spacing.md),
          TextField(
            controller: _next,
            obscureText: true,
            decoration: InputDecoration(labelText: l.newPassword, helperText: l.passwordChangeHint),
          ),
          const SizedBox(height: Spacing.md),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: Spacing.md),
              child: Text(describeError(l, _error!), style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          FilledButton(onPressed: _busy ? null : _change, child: Text(l.changePassword)),
        ],
      ),
    );
  }
}
