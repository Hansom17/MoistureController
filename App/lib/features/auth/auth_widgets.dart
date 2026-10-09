import 'package:flutter/material.dart';

import '../../app/theme/tokens.dart';
import '../../core/format.dart';

/// Centered narrow column used by Setup, Login and Join.
class AuthScaffold extends StatelessWidget {
  const AuthScaffold({super.key, required this.title, required this.children, this.subtitle});

  final String title;
  final String? subtitle;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Spacing.xl),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.eco, size: 48, color: theme.colorScheme.primary),
                  const SizedBox(height: Spacing.lg),
                  Text(title, style: theme.textTheme.headlineSmall, textAlign: TextAlign.center),
                  if (subtitle != null) ...[
                    const SizedBox(height: Spacing.sm),
                    Text(
                      subtitle!,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                  const SizedBox(height: Spacing.xl),
                  ...children,
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A form field with consistent spacing.
Widget authField(
  BuildContext context, {
  required TextEditingController controller,
  required String label,
  bool obscure = false,
  String? helper,
  TextInputAction action = TextInputAction.next,
  ValueChanged<String>? onSubmitted,
  ValueChanged<String>? onChanged,
  TextCapitalization capitalization = TextCapitalization.none,
}) => Padding(
  padding: const EdgeInsets.only(bottom: Spacing.md),
  child: TextField(
    controller: controller,
    obscureText: obscure,
    textInputAction: action,
    textCapitalization: capitalization,
    autocorrect: false,
    enableSuggestions: !obscure,
    onSubmitted: onSubmitted,
    onChanged: onChanged,
    decoration: InputDecoration(labelText: label, helperText: helper),
  ),
);

/// The name of this device for the token list, e.g. "Web browser".
String defaultDeviceName() => 'Web browser';

/// Error text under a form.
class FormError extends StatelessWidget {
  const FormError(this.error, {super.key});

  final Object? error;

  @override
  Widget build(BuildContext context) {
    if (error == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: Spacing.md),
      child: Text(
        describeError(context.l10n, error!),
        style: TextStyle(color: Theme.of(context).colorScheme.error),
      ),
    );
  }
}
