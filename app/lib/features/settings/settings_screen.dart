import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../core/settings.dart';
import '../../data/models.dart';
import '../../data/repositories/fake_moisture_repository.dart';
import '../../ui/common.dart';
import '../../ui/household_scope.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final themeMode = ref.watch(themeModeProvider);
    final locale = ref.watch(localeProvider);
    final repository = ref.watch(repositoryProvider);

    return Scaffold(
      appBar: AppBar(title: Text(l.navSettings)),
      body: HouseholdScope(
        builder: (context, household) => ListView(
          padding: const EdgeInsets.all(Spacing.lg),
          children: [
            SectionCard(
              title: l.appearance,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SegmentedButton<ThemeMode>(
                    segments: [
                      ButtonSegment(
                        value: ThemeMode.system,
                        label: Text(l.themeSystem),
                      ),
                      ButtonSegment(
                        value: ThemeMode.light,
                        label: Text(l.themeLight),
                      ),
                      ButtonSegment(
                        value: ThemeMode.dark,
                        label: Text(l.themeDark),
                      ),
                    ],
                    selected: {themeMode},
                    onSelectionChanged: (s) =>
                        ref.read(themeModeProvider.notifier).set(s.first),
                  ),
                  const SizedBox(height: Spacing.lg),
                  Text(
                    l.language,
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                  const SizedBox(height: Spacing.sm),
                  SegmentedButton<String>(
                    segments: [
                      ButtonSegment(value: '', label: Text(l.themeSystem)),
                      const ButtonSegment(value: 'de', label: Text('Deutsch')),
                      const ButtonSegment(value: 'en', label: Text('English')),
                    ],
                    selected: {locale?.languageCode ?? ''},
                    onSelectionChanged: (s) => ref
                        .read(localeProvider.notifier)
                        .set(s.first.isEmpty ? null : Locale(s.first)),
                  ),
                ],
              ),
            ),
            const SizedBox(height: Spacing.md),
            SectionCard(
              title: l.household,
              child: Column(
                children: [
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(household.name),
                    subtitle: Text('${l.timezone}: ${household.timezone}'),
                  ),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(l.yourRole),
                    trailing: Text(roleLabel(l, household.role)),
                  ),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.router_outlined),
                    title: Text(l.gatewayTitle),
                    subtitle: Text(switch (household.gateway) {
                      null => l.gatewayNone,
                      final gateway when gateway.online => l.deviceOnline,
                      final gateway =>
                        gateway.offlineSince == null
                            ? l.deviceOffline
                            : l.gatewayOfflineSince(
                                formatTime(context, gateway.offlineSince!),
                              ),
                    }),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => context.go('/settings/gateway'),
                  ),
                ],
              ),
            ),
            if (repository is FakeMoistureRepository) ...[
              const SizedBox(height: Spacing.md),
              SectionCard(
                title: l.demoSection,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(l.demoRole),
                    const SizedBox(height: Spacing.sm),
                    SegmentedButton<Role>(
                      showSelectedIcon: false,
                      segments: [
                        for (final r in Role.values)
                          ButtonSegment(value: r, label: Text(roleLabel(l, r))),
                      ],
                      selected: {household.role},
                      onSelectionChanged: (s) =>
                          repository.setRole(household.id, s.first),
                    ),
                    const SizedBox(height: Spacing.sm),
                    Text(
                      l.demoRoleHint,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
