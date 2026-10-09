/// RFC 9457 problem returned by the backend (App/specs.md Part A §6.1).
///
/// [type] is the stable machine-readable key the app maps to localized text.
class ApiProblem implements Exception {
  const ApiProblem(this.type, {this.status = 400, this.detail});

  final String type;
  final int status;
  final String? detail;

  /// No answer from the server at all (offline, wrong address, timeout).
  static const network = 'network';
  static const forbidden = 'forbidden';
  static const safetyLimit = 'safety_limit';
  static const householdFrozen = 'household_frozen';
  static const busy = 'busy';
  static const gatewayOffline = 'gateway_offline';
  static const noGateway = 'no_gateway';
  static const tooLate = 'too_late';
  static const invalidCode = 'invalid_code';
  static const gatewayExists = 'gateway_exists';
  static const reauthRequired = 'reauth_required';

  @override
  String toString() => 'ApiProblem($type, $status, $detail)';
}
