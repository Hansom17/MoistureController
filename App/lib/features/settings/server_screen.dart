import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/api_endpoint.dart';
import '../../core/format.dart';
import '../../data/discovery/api_discovery.dart';
import '../../ui/common.dart';

/// Which server the app talks to: found on the network, or typed in
/// (App/specs.md Part A §6.4.2). Only meaningful in the `local` flavor.
class ServerScreen extends ConsumerStatefulWidget {
  const ServerScreen({super.key});

  @override
  ConsumerState<ServerScreen> createState() => _ServerScreenState();
}

class _ServerScreenState extends ConsumerState<ServerScreen> {
  final _address = TextEditingController();
  String? _error;
  var _busy = false;

  @override
  void dispose() {
    _address.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final l = context.l10n;
    setState(() {
      _busy = true;
      _error = null;
    });
    final error = await ref
        .read(apiEndpointProvider.notifier)
        .setManual(_address.text);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = switch (error) {
        null => null,
        ManualAddressError.invalid => l.serverAddressInvalid,
        ManualAddressError.notLocal => l.serverAddressNotLocal,
        ManualAddressError.noAnswer => l.serverAddressNoAnswer,
      };
    });
    if (error == null) _address.clear();
  }

  /// §6.4.3: a dev server takes unsigned logins; confirm before switching to one
  /// that is not the remembered server.
  Future<void> _select(ApiServer server, ApiServer? current) async {
    final l = context.l10n;
    if (server.auth == 'dev' && server != current) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(l.serverDevWarningTitle),
          content: Text(l.serverDevWarningBody),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text(l.cancel),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: Text(l.serverContinue),
            ),
          ],
        ),
      );
      if (ok != true) return;
    }
    await ref.read(apiEndpointProvider.notifier).select(server);
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final state = ref.watch(apiEndpointProvider);
    final current = state is ApiConnected ? state.server : null;
    final choices = state is ApiChoose ? state.servers : const <ApiServer>[];
    final searching = state is ApiSearching;

    String authLabel(ApiServer s) => switch (s.auth) {
      'dev' => l.serverAuthDev,
      'firebase' => l.serverAuthFirebase,
      _ => '',
    };

    return Scaffold(
      appBar: AppBar(
        title: Text(l.serverTitle),
        leading: BackButton(
          onPressed: () =>
              context.canPop() ? context.pop() : context.go('/settings'),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(Spacing.lg),
        children: [
          SectionCard(
            title: l.serverCurrent,
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                current == null ? Icons.wifi_off : Icons.dns_outlined,
              ),
              title: Text(
                current == null
                    ? (searching ? l.connSearching : l.connUnreachable)
                    : current.name,
              ),
              subtitle: current == null
                  ? null
                  : Text('${current.address} · ${authLabel(current)}'),
              trailing: searching
                  ? const SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : null,
            ),
          ),
          if (choices.isNotEmpty) ...[
            const SizedBox(height: Spacing.md),
            SectionCard(
              title: l.serverFound,
              child: Column(
                children: [
                  for (final s in choices)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.dns_outlined),
                      title: Text(s.name),
                      subtitle: Text('${s.address} · ${authLabel(s)}'),
                      trailing: TextButton(
                        onPressed: () => _select(s, current),
                        child: Text(l.serverUseThis),
                      ),
                    ),
                ],
              ),
            ),
          ],
          const SizedBox(height: Spacing.md),
          OutlinedButton.icon(
            onPressed: searching
                ? null
                : ref.read(apiEndpointProvider.notifier).search,
            icon: const Icon(Icons.refresh),
            label: Text(l.serverSearchAgain),
          ),
          const SizedBox(height: Spacing.md),
          SectionCard(
            title: l.serverAddress,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _address,
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  decoration: InputDecoration(
                    hintText: l.serverAddressHint,
                    errorText: _error,
                  ),
                  onSubmitted: (_) => _submit(),
                ),
                const SizedBox(height: Spacing.sm),
                FilledButton(
                  onPressed: _busy ? null : _submit,
                  child: Text(l.serverContinue),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
