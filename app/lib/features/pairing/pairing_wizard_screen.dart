import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../ui/household_scope.dart';
import 'label_scanner.dart';
import 'pairing_controller.dart';
import 'protocol/pairing_label.dart';

/// Add a device over Bluetooth (App_Specs §11, contracts/ble.md §6).
class PairingWizardScreen extends StatelessWidget {
  const PairingWizardScreen({super.key});

  @override
  Widget build(BuildContext context) =>
      HouseholdScope(builder: (context, household) => _Wizard(household: household));
}

class _Wizard extends ConsumerWidget {
  const _Wizard({required this.household});

  final Household household;

  Future<bool> _confirmLeave(BuildContext context, PairingState s) async {
    final unfinished = s.step != PairingStep.done && s.step != PairingStep.label &&
        s.step != PairingStep.name;
    if (!unfinished || s.step == PairingStep.failed) return true;
    final l = context.l10n;
    return await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: Text(l.pairCancelTitle),
            content: Text(l.pairCancelBody),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: Text(l.pairKeepGoing),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: Text(l.cancel),
              ),
            ],
          ),
        ) ??
        false;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final provider = pairingControllerProvider(household.id);
    final s = ref.watch(provider);
    final ctl = ref.read(provider.notifier);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        if (await _confirmLeave(context, s) && context.mounted) {
          await ctl.cancel();
          if (context.mounted) context.pop();
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(l.pairAddDevice),
          leading: CloseButton(
            onPressed: () async {
              if (await _confirmLeave(context, s) && context.mounted) {
                await ctl.cancel();
                if (context.mounted) context.pop();
              }
            },
          ),
        ),
        body: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: ListView(
              padding: const EdgeInsets.all(Spacing.lg),
              children: [
                switch (s.step) {
                  PairingStep.label => _LabelStep(onLabel: ctl.setLabel),
                  PairingStep.name => _NameStep(onStart: ctl.begin),
                  PairingStep.working => _Progress(text: _workText(context, s)),
                  PairingStep.wifi => _WifiStep(state: s, onSubmit: ctl.submitWifi),
                  PairingStep.testing => _Progress(
                    text: l.pairTestingTitle,
                    body: l.pairTestingBody,
                  ),
                  PairingStep.finishing => _Progress(text: l.pairWaitingOnline),
                  PairingStep.done => _DoneStep(state: s, household: household),
                  PairingStep.failed => _FailedStep(state: s, onRetry: ctl.retry, onReset: ctl.reset),
                },
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _workText(BuildContext context, PairingState s) {
    final l = context.l10n;
    return switch (s.work) {
      PairingWork.creating => l.pairCreating,
      PairingWork.finding => l.pairFinding(s.label?.bleName ?? ''),
      PairingWork.handshake => l.pairHandshake,
      PairingWork.scanning => l.pairScanning,
    };
  }
}

// --- steps ----------------------------------------------------------------------------------

class _LabelStep extends ConsumerStatefulWidget {
  const _LabelStep({required this.onLabel});

  final void Function(PairingLabel) onLabel;

  @override
  ConsumerState<_LabelStep> createState() => _LabelStepState();
}

class _LabelStepState extends ConsumerState<_LabelStep> {
  final _name = TextEditingController();
  final _code = TextEditingController();
  var _manual = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _code.dispose();
    super.dispose();
  }

  void _scanned(String text) {
    final label = PairingLabel.tryParse(text);
    if (label != null) {
      widget.onLabel(label);
    } else if (_error == null && mounted) {
      setState(() => _error = context.l10n.pairLabelInvalid);
    }
  }

  void _submitManual() {
    final label = PairingLabel.fromManual(_name.text, _code.text);
    if (label == null) {
      setState(() => _error = context.l10n.pairLabelInvalid);
    } else {
      widget.onLabel(label);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(l.pairLabelTitle, style: theme.textTheme.titleLarge),
        const SizedBox(height: Spacing.sm),
        Text(l.pairLabelBody),
        const SizedBox(height: Spacing.lg),
        if (!_manual)
          AspectRatio(
            aspectRatio: 1,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(Radii.card),
              child: ref.watch(labelScannerBuilderProvider)(_scanned),
            ),
          ),
        if (_error != null) ...[
          const SizedBox(height: Spacing.md),
          Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
        ],
        const SizedBox(height: Spacing.md),
        if (_manual) ...[
          TextField(
            controller: _name,
            textCapitalization: TextCapitalization.characters,
            autocorrect: false,
            decoration: InputDecoration(labelText: l.pairManualName, hintText: 'MC-3F9A'),
          ),
          const SizedBox(height: Spacing.md),
          TextField(
            controller: _code,
            textCapitalization: TextCapitalization.characters,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(labelText: l.pairManualCode),
            onSubmitted: (_) => _submitManual(),
          ),
          const SizedBox(height: Spacing.lg),
          FilledButton(onPressed: _submitManual, child: Text(l.pairContinue)),
        ],
        TextButton(
          onPressed: () => setState(() {
            _manual = !_manual;
            _error = null;
          }),
          child: Text(_manual ? l.pairLabelTitle : l.pairManualToggle),
        ),
      ],
    );
  }
}

class _NameStep extends StatefulWidget {
  const _NameStep({required this.onStart});

  final void Function(String name) onStart;

  @override
  State<_NameStep> createState() => _NameStepState();
}

class _NameStepState extends State<_NameStep> {
  final _name = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  void _go() {
    final name = _name.text.trim();
    if (name.isNotEmpty) widget.onStart(name);
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(l.pairNameTitle, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: Spacing.lg),
        TextField(
          controller: _name,
          autofocus: true,
          maxLength: 100,
          decoration: InputDecoration(hintText: l.pairNameHint),
          onSubmitted: (_) => _go(),
        ),
        const SizedBox(height: Spacing.md),
        FilledButton(onPressed: _go, child: Text(l.pairStart)),
      ],
    );
  }
}

class _Progress extends StatelessWidget {
  const _Progress({required this.text, this.body});

  final String text;
  final String? body;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: Spacing.xl),
    child: Column(
      children: [
        const CircularProgressIndicator(),
        const SizedBox(height: Spacing.lg),
        Text(text, style: Theme.of(context).textTheme.titleMedium, textAlign: TextAlign.center),
        if (body != null) ...[
          const SizedBox(height: Spacing.sm),
          Text(body!, textAlign: TextAlign.center),
        ],
      ],
    ),
  );
}

class _WifiStep extends StatefulWidget {
  const _WifiStep({required this.state, required this.onSubmit});

  final PairingState state;
  final void Function(String ssid, String password) onSubmit;

  @override
  State<_WifiStep> createState() => _WifiStepState();
}

class _WifiStepState extends State<_WifiStep> {
  final _ssid = TextEditingController();
  final _password = TextEditingController();
  var _obscure = true;

  @override
  void dispose() {
    _ssid.dispose();
    _password.dispose();
    super.dispose();
  }

  String? _testMessage(BuildContext context) {
    final t = widget.state.testError;
    if (t == null) return null;
    final l = context.l10n;
    if (!t.wifiOk) return l.pairTestWifiFailed;
    return l.pairTestMqttFailed(t.detail.isEmpty ? '?' : t.detail);
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    final error = _testMessage(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(l.pairWifiTitle, style: theme.textTheme.titleLarge),
        const SizedBox(height: Spacing.sm),
        Text(l.pairWifiBody),
        if (error != null) ...[
          const SizedBox(height: Spacing.md),
          Text(error, style: TextStyle(color: theme.colorScheme.error)),
        ],
        const SizedBox(height: Spacing.md),
        for (final n in widget.state.networks)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(n.secure ? Icons.wifi_lock_outlined : Icons.wifi),
            title: Text(n.ssid),
            subtitle: Text('${n.rssi} dBm'),
            selected: _ssid.text == n.ssid,
            onTap: () => setState(() => _ssid.text = n.ssid),
          ),
        const SizedBox(height: Spacing.sm),
        TextField(
          controller: _ssid,
          autocorrect: false,
          enableSuggestions: false,
          decoration: InputDecoration(labelText: l.pairSsidLabel),
        ),
        const SizedBox(height: Spacing.md),
        TextField(
          controller: _password,
          obscureText: _obscure,
          autocorrect: false,
          enableSuggestions: false,
          decoration: InputDecoration(
            labelText: l.pairPasswordLabel,
            suffixIcon: IconButton(
              icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
              onPressed: () => setState(() => _obscure = !_obscure),
            ),
          ),
          onSubmitted: (_) => _submit(),
        ),
        const SizedBox(height: Spacing.lg),
        FilledButton(onPressed: _submit, child: Text(l.pairConnect)),
      ],
    );
  }

  void _submit() {
    final ssid = _ssid.text.trim();
    if (ssid.isNotEmpty) widget.onSubmit(ssid, _password.text);
  }
}

class _DoneStep extends StatelessWidget {
  const _DoneStep({required this.state, required this.household});

  final PairingState state;
  final Household household;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: Spacing.lg),
        Icon(Icons.check_circle_outline, size: 56, color: theme.colorScheme.primary),
        const SizedBox(height: Spacing.md),
        Text(l.pairDoneTitle, style: theme.textTheme.titleLarge, textAlign: TextAlign.center),
        const SizedBox(height: Spacing.sm),
        Text(
          state.stillWaiting ? l.pairDoneSlow : l.pairDoneBody(state.name),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: Spacing.xl),
        FilledButton(
          onPressed: () {
            final id = state.deviceId;
            context.go(id == null ? '/devices' : '/devices/$id');
          },
          child: Text(l.pairOpenDevice),
        ),
      ],
    );
  }
}

class _FailedStep extends StatelessWidget {
  const _FailedStep({required this.state, required this.onRetry, required this.onReset});

  final PairingState state;
  final VoidCallback onRetry;
  final VoidCallback onReset;

  String _message(BuildContext context) {
    final l = context.l10n;
    return switch (state.failure) {
      PairingFailure.noGateway => l.pairFailNoGateway,
      PairingFailure.gatewayOffline => l.pairFailGatewayOffline,
      PairingFailure.notFound => l.pairFailNotFound,
      PairingFailure.wrongCode => l.pairFailWrongCode,
      PairingFailure.connection => l.pairFailConnection,
      PairingFailure.bluetoothOff => l.pairFailBluetoothOff,
      PairingFailure.bluetoothDenied => l.pairFailBluetoothDenied,
      PairingFailure.unsupported => l.pairFailUnsupported,
      _ => l.pairFailOther,
    };
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: Spacing.lg),
        Icon(Icons.error_outline, size: 56, color: theme.colorScheme.error),
        const SizedBox(height: Spacing.md),
        Text(_message(context), style: theme.textTheme.titleMedium, textAlign: TextAlign.center),
        if (state.detail.isNotEmpty) ...[
          const SizedBox(height: Spacing.sm),
          Text(state.detail, style: theme.textTheme.bodySmall, textAlign: TextAlign.center),
        ],
        const SizedBox(height: Spacing.xl),
        if (state.canRetry)
          FilledButton(onPressed: onRetry, child: Text(l.pairTryAgain))
        else if (state.failure == PairingFailure.wrongCode)
          FilledButton(onPressed: onReset, child: Text(l.pairTryAgain)),
        TextButton(onPressed: () => context.pop(), child: Text(l.pairClose)),
      ],
    );
  }
}
