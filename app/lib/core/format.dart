import 'package:flutter/widgets.dart';
import 'package:intl/intl.dart';

import '../data/api_problem.dart';
import '../data/models.dart';
import '../l10n/app_localizations.dart';

extension L10nX on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
}

/// "just now", "12 min ago", "2 h ago", "3 d ago".
String formatAgo(AppLocalizations l, DateTime at, {DateTime? now}) {
  final d = (now ?? DateTime.now()).difference(at);
  if (d.inMinutes < 1) return l.justNow;
  if (d.inHours < 1) return l.minutesAgo(d.inMinutes);
  if (d.inDays < 1) return l.hoursAgo(d.inHours);
  return l.daysAgo(d.inDays);
}

/// Clock time in the user's locale, e.g. "14:32" / "2:32 PM".
String formatTime(BuildContext context, DateTime at) =>
    DateFormat.Hm(Localizations.localeOf(context).toString()).format(at);

String roleLabel(AppLocalizations l, Role role) => switch (role) {
  Role.viewer => l.roleViewer,
  Role.member => l.roleMember,
  Role.admin => l.roleAdmin,
  Role.owner => l.roleOwner,
};

/// Maps backend problem types to localized messages (App_Specs §6.1).
String describeError(AppLocalizations l, Object error) {
  if (error is ApiProblem) {
    return switch (error.type) {
      ApiProblem.forbidden => l.errorForbidden,
      ApiProblem.safetyLimit => l.errorSafetyLimit,
      ApiProblem.gatewayOffline => l.errorGatewayOffline,
      ApiProblem.tooLate => l.errorTooLate,
      ApiProblem.busy => l.errorBusy,
      ApiProblem.invalidCode => l.errorInvalidCode,
      ApiProblem.gatewayExists => l.errorGatewayExists,
      ApiProblem.noGateway => l.errorNoGateway,
      ApiProblem.reauthRequired => l.errorReauth,
      _ => error.detail ?? l.errorGeneric,
    };
  }
  return l.errorGeneric;
}
