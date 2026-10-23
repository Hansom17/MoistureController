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

/// "3 d 4 h", "5 h 12 min", "42 min".
String formatDuration(AppLocalizations l, Duration d) {
  if (d.inDays >= 1) return '${d.inDays} d ${d.inHours % 24} h';
  if (d.inHours >= 1) return '${d.inHours} h ${d.inMinutes % 60} min';
  return '${d.inMinutes} min';
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

/// Why a rule did not water ("cooldown", "quiet_hours", ...), localized.
String skipReasonLabel(AppLocalizations l, String? reason) => switch (reason) {
  'cooldown' => l.skipCooldown,
  'quiet_hours' => l.skipQuietHours,
  'daily_limit' => l.skipDailyLimit,
  'pending_command' => l.skipPending,
  'sensor_error' => l.skipSensorError,
  'no_pump' => l.skipNoPump,
  'clock_not_synced' => l.skipClock,
  _ => reason ?? '—',
};

/// Maps backend problem types to localized messages (App/specs.md Part A §6.1).
String describeError(AppLocalizations l, Object error) {
  if (error is ApiProblem) {
    return switch (error.type) {
      ApiProblem.forbidden => l.errorForbidden,
      ApiProblem.safetyLimit => l.errorSafetyLimit,
      ApiProblem.busy => l.errorBusy,
      ApiProblem.conflict => error.detail ?? l.errorConflict,
      ApiProblem.deviceNotReady => l.errorDeviceNotReady,
      ApiProblem.deviceSafeMode => l.errorDeviceSafeMode,
      ApiProblem.slotNotActuator => l.errorSlotNotActuator,
      ApiProblem.invalidCredentials => l.errorInvalidCredentials,
      ApiProblem.rateLimited => l.errorRateLimited,
      ApiProblem.reauthRequired => l.errorReauth,
      ApiProblem.hubUnavailable => l.errorHubUnavailable,
      ApiProblem.hubTimeout => l.errorHubTimeout,
      ApiProblem.incompatibleHub => l.errorIncompatibleHub,
      ApiProblem.invalidSetupCode => l.errorInvalidSetupCode,
      ApiProblem.alreadySetUp => l.errorAlreadySetUp,
      ApiProblem.invalidInvite => l.errorInvalidInvite,
      ApiProblem.network => l.errorNetwork,
      _ => error.detail ?? l.errorGeneric,
    };
  }
  return l.errorGeneric;
}
