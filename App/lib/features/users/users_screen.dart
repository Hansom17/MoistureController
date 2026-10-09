import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/tokens.dart';
import '../../core/actions.dart';
import '../../core/app_data.dart';
import '../../core/format.dart';
import '../../core/session.dart';
import '../../data/models.dart';
import '../../ui/app_scope.dart';
import '../../ui/common.dart';
import '../../ui/reauth.dart';

/// Users, invites and the audit log (App/specs.md Part A §12).
class UsersScreen extends StatelessWidget {
  const UsersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return AppScope(
      builder: (context, me) => Scaffold(
        appBar: AppBar(title: Text(l.usersTitle)),
        body: ListView(
          padding: const EdgeInsets.all(Spacing.lg),
          children: [
            _UsersCard(me: me),
            const SizedBox(height: Spacing.md),
            _InvitesCard(me: me),
            const SizedBox(height: Spacing.md),
            const _AuditCard(),
          ],
        ),
      ),
    );
  }
}

class _UsersCard extends ConsumerWidget {
  const _UsersCard({required this.me});

  final AppUser me;

  /// Whether [me] may manage [u] (admins: members and viewers; the owner: everybody but themself).
  bool _manages(AppUser u) =>
      u.id != me.id && u.role != Role.owner && (me.role == Role.owner || u.role.index < Role.admin.index);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final users = ref.watch(usersProvider);
    return SectionCard(
      title: l.usersTitle,
      child: AsyncBody(
        value: users,
        onRetry: () => ref.invalidate(usersProvider),
        data: (users) => Column(
          children: [
            for (final u in users)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(u.disabled ? Icons.person_off_outlined : Icons.person_outline),
                title: Text(u.displayName),
                subtitle: Text('@${u.username} · ${roleLabel(l, u.role)}${u.disabled ? ' · ${l.userDisabled}' : ''}'),
                trailing: _manages(u)
                    ? PopupMenuButton<String>(
                        onSelected: (a) => _act(context, ref, u, a),
                        itemBuilder: (_) => [
                          PopupMenuItem(value: 'role', child: Text(l.changeRole)),
                          PopupMenuItem(value: 'disable', child: Text(u.disabled ? l.enableUser : l.disableUser)),
                          if (me.role == Role.owner && !u.disabled)
                            PopupMenuItem(value: 'owner', child: Text(l.transferOwnership)),
                          PopupMenuItem(value: 'remove', child: Text(l.removeUser)),
                        ],
                      )
                    : null,
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _act(BuildContext context, WidgetRef ref, AppUser u, String action) async {
    final l = context.l10n;
    final actions = ref.read(actionsProvider);
    try {
      switch (action) {
        case 'role':
          final roles = me.role == Role.owner ? [Role.viewer, Role.member, Role.admin] : [Role.viewer, Role.member];
          final role = await showDialog<Role>(
            context: context,
            builder: (context) => SimpleDialog(
              title: Text(l.changeRole),
              children: [
                for (final r in roles)
                  SimpleDialogOption(onPressed: () => Navigator.pop(context, r), child: Text(roleLabel(l, r))),
              ],
            ),
          );
          if (role == null || role == u.role || !context.mounted) return;
          await withReauth(context, ref, () => actions.updateUser(u.id, role: role));
        case 'disable':
          await actions.updateUser(u.id, disabled: !u.disabled);
        case 'owner':
          if (!await _confirm(context, l.transferOwnership, l.transferOwnershipBody(u.displayName)) || !context.mounted) return;
          await withReauth(context, ref, () => actions.transferOwnership(u.id));
        case 'remove':
          if (!await _confirm(context, l.removeUser, l.removeUserBody(u.displayName)) || !context.mounted) return;
          await withReauth(context, ref, () => actions.deleteUser(u.id));
      }
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}

Future<bool> _confirm(BuildContext context, String title, String body) async =>
    await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(body),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(context.l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(context.l10n.confirm)),
        ],
      ),
    ) ??
    false;

class _InvitesCard extends ConsumerWidget {
  const _InvitesCard({required this.me});

  final AppUser me;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final invites = ref.watch(invitesProvider);
    return SectionCard(
      title: l.invitesTitle,
      trailing: IconButton(
        tooltip: l.createInvite,
        icon: const Icon(Icons.person_add_alt),
        onPressed: () => _create(context, ref),
      ),
      child: AsyncBody(
        value: invites,
        onRetry: () => ref.invalidate(invitesProvider),
        data: (list) {
          final shown = list.where((i) => i.status == 'open').toList();
          if (shown.isEmpty) return Text(l.noInvites);
          return Column(
            children: [
              for (final i in shown)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.mail_outline),
                  title: Text(roleLabel(l, i.role)),
                  subtitle: Text(l.inviteExpires(formatTime(context, i.expiresAt))),
                  trailing: IconButton(
                    tooltip: l.revokeInvite,
                    icon: const Icon(Icons.close),
                    onPressed: () => ref.read(actionsProvider).revokeInvite(i.id),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final l = context.l10n;
    final roles = me.role == Role.owner ? [Role.viewer, Role.member, Role.admin] : [Role.viewer, Role.member];
    final role = await showDialog<Role>(
      context: context,
      builder: (context) => SimpleDialog(
        title: Text(l.inviteAs),
        children: [
          for (final r in roles)
            SimpleDialogOption(onPressed: () => Navigator.pop(context, r), child: Text(roleLabel(l, r))),
        ],
      ),
    );
    if (role == null || !context.mounted) return;
    try {
      final created = await ref.read(actionsProvider).createInvite(role);
      if (!context.mounted) return;
      final link = created.link(ref.read(originProvider));
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(l.inviteCreated),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l.inviteShownOnce),
              const SizedBox(height: Spacing.md),
              SelectableText(link, key: const ValueKey('invite-link')),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: link));
                showSnackBar(context, l.copied);
              },
              child: Text(l.copyLink),
            ),
            FilledButton(onPressed: () => Navigator.pop(context), child: Text(l.done)),
          ],
        ),
      );
    } catch (e) {
      if (context.mounted) showErrorSnackBar(context, e);
    }
  }
}

class _AuditCard extends ConsumerWidget {
  const _AuditCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l = context.l10n;
    final audit = ref.watch(auditProvider);
    return SectionCard(
      title: l.auditTitle,
      child: AsyncBody(
        value: audit,
        onRetry: () => ref.invalidate(auditProvider),
        data: (list) => list.isEmpty
            ? Text(l.noAudit)
            : Column(
                children: [
                  for (final a in list.take(20))
                    ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.history),
                      title: Text(a.action.replaceAll('_', ' ')),
                      subtitle: Text(formatAgo(l, a.at)),
                    ),
                ],
              ),
      ),
    );
  }
}
