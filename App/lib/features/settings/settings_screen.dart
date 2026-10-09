import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/tokens.dart';
import '../../core/api_endpoint.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../core/permissions.dart';
import '../../core/session.dart';
import '../../core/settings.dart';
import '../../data/models.dart';
import '../../data/repositories/fake_moisture_repository.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final themeMode = ref.watch(themeModeProvider);
    final locale = ref.watch(localeProvider);
    final repository = ref.watch(repositoryProvider);

    Widget link(IconData icon, String title, String path, {String? subtitle}) => ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(icon),
      title: Text(title),
      subtitle: subtitle == null ? null : Text(subtitle),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => context.go(path),
    );

    return Scaffold(
      appBar: AppBar(title: Text(l.navSettings)),
      body: AppScope(
        builder: (context, user) {
          final installation = ref.watch(installationProvider).value;
          final role = user.role;
          return ListView(
            padding: const EdgeInsets.all(Spacing.lg),
            children: [
              SectionCard(
                title: l.account,
                child: Column(
                  children: [
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.person_outline),
                      title: Text(user.displayName),
                      subtitle: Text('@${user.username}'),
                      trailing: Text(roleLabel(l, role)),
                    ),
                    link(Icons.devices_outlined, l.myDevices, '/settings/tokens'),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.logout),
                      title: Text(l.signOut),
                      onTap: () => ref.read(sessionProvider.notifier).signOut(),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: Spacing.md),
              SectionCard(
                title: l.installation,
                child: Column(
                  children: [
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(installation?.name ?? '—'),
                      subtitle: installation == null ? null : Text('${l.timezone}: ${installation.timezone}'),
                    ),
                    link(Icons.router_outlined, l.gatewayTitle, '/settings/gateway'),
                    if (can(role, AppAction.manageUsers)) link(Icons.group_outlined, l.usersTitle, '/settings/users'),
                    if (can(role, AppAction.manageInstallation))
                      link(Icons.tune, l.installationSettings, '/settings/installation'),
                    if (can(role, AppAction.backup)) link(Icons.save_alt, l.dataTitle, '/settings/data'),
                  ],
                ),
              ),
              const SizedBox(height: Spacing.md),
              SectionCard(
                title: l.appearance,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    SegmentedButton<ThemeMode>(
                      segments: [
                        ButtonSegment(value: ThemeMode.system, label: Text(l.themeSystem)),
                        ButtonSegment(value: ThemeMode.light, label: Text(l.themeLight)),
                        ButtonSegment(value: ThemeMode.dark, label: Text(l.themeDark)),
                      ],
                      selected: {themeMode},
                      onSelectionChanged: (s) => ref.read(themeModeProvider.notifier).set(s.first),
                    ),
                    const SizedBox(height: Spacing.lg),
                    Text(l.language, style: Theme.of(context).textTheme.labelLarge),
                    const SizedBox(height: Spacing.sm),
                    SegmentedButton<String>(
                      segments: [
                        ButtonSegment(value: '', label: Text(l.themeSystem)),
                        const ButtonSegment(value: 'de', label: Text('Deutsch')),
                        const ButtonSegment(value: 'en', label: Text('English')),
                      ],
                      selected: {locale?.languageCode ?? ''},
                      onSelectionChanged: (s) =>
                          ref.read(localeProvider.notifier).set(s.first.isEmpty ? null : Locale(s.first)),
                    ),
                  ],
                ),
              ),
              if (ref.watch(apiEndpointProvider) is! ApiFixed) ...[
                const SizedBox(height: Spacing.md),
                SectionCard(
                  title: l.serverTitle,
                  child: link(Icons.dns_outlined, l.serverSubtitle, '/server'),
                ),
              ],
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
                        segments: [for (final r in Role.values) ButtonSegment(value: r, label: Text(roleLabel(l, r)))],
                        selected: {role},
                        onSelectionChanged: (s) {
                          repository.setRole(s.first);
                          ref.read(sessionProvider.notifier).refresh();
                        },
                      ),
                      const SizedBox(height: Spacing.sm),
                      Text(l.demoRoleHint, style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}
