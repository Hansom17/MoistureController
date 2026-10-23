/// RFC 9457 problem returned by the api (App/specs.md Part A §6.1).
///
/// [type] is the stable machine-readable key (`code` in the JSON) the app maps to localized text.
class ApiProblem implements Exception {
  const ApiProblem(this.type, {this.status = 400, this.detail});

  final String type;
  final int status;
  final String? detail;

  /// No answer from the server at all (offline, wrong address, timeout).
  static const network = 'network';
  static const unauthorized = 'unauthorized';
  static const invalidCredentials = 'invalid_credentials';
  static const forbidden = 'forbidden';
  static const safetyLimit = 'safety_limit';
  static const busy = 'busy';
  static const conflict = 'conflict';
  static const deviceNotReady = 'device_not_ready';
  static const deviceSafeMode = 'device_safe_mode';
  static const slotNotActuator = 'slot_not_actuator';
  static const validation = 'validation';
  static const rateLimited = 'rate_limited';
  static const reauthRequired = 'reauth_required';
  static const hubUnavailable = 'hub_unavailable';
  static const hubTimeout = 'hub_timeout';
  static const incompatibleHub = 'incompatible_hub';
  static const invalidSetupCode = 'invalid_setup_code';
  static const alreadySetUp = 'already_set_up';
  static const invalidInvite = 'invalid_invite';
  static const notFound = 'not_found';

  @override
  String toString() => 'ApiProblem($type, $status, $detail)';
}
