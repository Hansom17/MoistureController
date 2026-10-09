import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';

/// Name, timezone, battery threshold and Telegram (owner; App/specs.md Part A §4, §13).
class InstallationScreen extends StatelessWidget {
  const InstallationScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AppScope(
      builder: (context, user) => Scaffold(
        appBar: AppBar(title: Text(l.installationSettings)),
        body: Consumer(
          builder: (context, ref, _) => AsyncBody(
            value: ref.watch(installationProvider),
            onRetry: () => ref.invalidate(installationProvider),
            data: (i) => _Form(installation: i),
          ),
        ),
      ),
    );
  }
}

class _Form extends ConsumerStatefulWidget {
  const _Form({required this.installation});

  final Installation installation;

  @override
  ConsumerState<_Form> createState() => _FormState();
}

class _FormState extends ConsumerState<_Form> {
  late final _name = TextEditingController(text: widget.installation.name);
  late final _timezone = TextEditingController(text: widget.installation.timezone);
  late final _battery = TextEditingController(text: '${widget.installation.batteryLowMv}');
  final _token = TextEditingController();
  final _chat = TextEditingController();
  Object? _error;
  var _busy = false;

  @override
  void dispose() {
    for (final c in [_name, _timezone, _battery, _token, _chat]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final l = context.l10n;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(actionsProvider).updateInstallation(
        name: _name.text.trim(),
        timezone: _timezone.text.trim(),
        batteryLowMv: int.tryParse(_battery.text),
        telegramToken: _token.text.isEmpty ? null : _token.text.trim(),
        telegramChatId: _chat.text.isEmpty ? null : _chat.text.trim(),
      );
      if (!mounted) return;
      _token.clear();
      showSnackBar(context, l.saved);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return ListView(
      padding: const EdgeInsets.all(Spacing.lg),
      children: [
        SectionCard(
          title: l.installation,
          child: Column(
            children: [
              TextField(controller: _name, decoration: InputDecoration(labelText: l.installationName)),
              const SizedBox(height: Spacing.md),
              TextField(controller: _timezone, decoration: InputDecoration(labelText: l.timezone, helperText: l.timezoneHint)),
              const SizedBox(height: Spacing.md),
              TextField(
                controller: _battery,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(labelText: l.batteryThreshold, suffixText: 'mV'),
              ),
            ],
          ),
        ),
        const SizedBox(height: Spacing.md),
        SectionCard(
          title: l.telegramTitle,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(widget.installation.telegramConfigured ? l.telegramConfigured : l.telegramNotConfigured),
              const SizedBox(height: Spacing.md),
              TextField(
                controller: _token,
                obscureText: true,
                decoration: InputDecoration(labelText: l.telegramToken, helperText: l.telegramTokenHint),
              ),
              const SizedBox(height: Spacing.md),
              TextField(controller: _chat, decoration: InputDecoration(labelText: l.telegramChat)),
            ],
          ),
        ),
        const SizedBox(height: Spacing.lg),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: Spacing.md),
            child: Text(describeError(l, _error!), style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        FilledButton(onPressed: _busy ? null : _save, child: Text(l.save)),
      ],
    );
  }
}
