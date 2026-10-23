import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/format.dart';
import '../../core/permissions.dart';
import '../../core/session.dart';
import '../../data/api/download.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';
import '../../ui/reauth.dart';

/// Export (owner, with password) and backup (admin) (App/specs.md Part A §4).
class DataScreen extends StatelessWidget {
  const DataScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AppScope(
      builder: (context, user) => Scaffold(
        appBar: AppBar(title: Text(l.dataTitle)),
        body: Consumer(
          builder: (context, ref, _) => ListView(
            padding: const EdgeInsets.all(Spacing.lg),
            children: [
              SectionCard(
                title: l.backupTitle,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(l.backupBody),
                    const SizedBox(height: Spacing.md),
                    FilledButton.tonalIcon(
                      icon: const Icon(Icons.save_alt),
                      label: Text(l.backupNow),
                      onPressed: () async {
                        try {
                          await ref.read(repositoryProvider).backup();
                          if (context.mounted) showSnackBar(context, l.backupDone);
                        } catch (e) {
                          if (context.mounted) showErrorSnackBar(context, e);
                        }
                      },
                    ),
                  ],
                ),
              ),
              if (can(user.role, AppAction.exportData)) ...[
                const SizedBox(height: Spacing.md),
                SectionCard(
                  title: l.exportTitle,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(l.exportBody),
                      const SizedBox(height: Spacing.md),
                      FilledButton.icon(
                        icon: const Icon(Icons.download),
                        label: Text(l.exportStart),
                        onPressed: () async {
                          try {
                            final bytes = await withReauth(context, ref, () => ref.read(repositoryProvider).exportData());
                            if (bytes == null || !context.mounted) return;
                            final saved = saveFile('moisture-export.zip', bytes, mime: 'application/zip');
                            showSnackBar(context, saved ? l.exportDone : l.exportUnsupported);
                          } catch (e) {
                            if (context.mounted) showErrorSnackBar(context, e);
                          }
                        },
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
