import '../models.dart';

/// Everything the app reads from or writes to the gateway's api.
///
/// Screens never use this directly — only through providers and actions (App/specs.md Part A §3).
/// Implementations: [FakeMoistureRepository] (no backend) and [ApiMoistureRepository] (REST + SSE).
abstract interface class MoistureRepository {
  // ---- before and around sign-in ----------------------------------------------------------
  Future<GatewayMeta> meta();

  /// First start of a gateway: creates the owner (needs the setup code from the api's log).
  Future<Session> setup({
    required String setupCode,
    required String name,
    required String timezone,
    required String username,
    required String password,
    String displayName = '',
  });
  Future<Session> login({
    required String username,
    required String password,
    String deviceName = '',
  });
  Future<InvitePreview> previewInvite(String code);
  Future<Session> acceptInvite({
    required String code,
    required String username,
    required String password,
    String displayName = '',
    String deviceName = '',
  });

  /// The token to send; null signs out locally. Set by the session after login or on start.
  void useToken(String? token);

  /// Validates the stored token.
  Future<AppUser> me();
  Future<void> logout();
  Future<AppUser> updateMe({String? displayName});
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  });

  /// Proves the password for sensitive actions; the proof is used for the next request that needs it.
  Future<void> reauth(String password);

  // ---- tokens, users, invites, audit -------------------------------------------------------
  Future<List<TokenInfo>> tokens();
  Future<void> revokeToken(String id);
  Future<List<AppUser>> users();
  Future<AppUser> updateUser(
    String id, {
    Role? role,
    String? displayName,
    bool? disabled,
  });
  Future<void> deleteUser(String id);
  Future<void> transferOwnership(String userId);
  Future<List<Invite>> invites();
  Future<CreatedInvite> createInvite(Role role, {Duration? expiresIn});
  Future<void> revokeInvite(String id);
  Future<List<AuditEntry>> audit({int? before, int limit = 100});

  // ---- installation and gateway --------------------------------------------------------------
  Future<Installation> installation();
  Future<Installation> updateInstallation({
    String? name,
    String? timezone,
    int? batteryLowMv,
    int? batteryCriticalMv,
    String? telegramToken,
    String? telegramChatId,
  });
  Future<GatewayStatus> gatewayStatus();
  Future<void> backup();

  /// The export ZIP (owner, needs [reauth]).
  Future<List<int>> exportData();

  // ---- plants --------------------------------------------------------------------------------
  Future<List<Plant>> plants();
  Future<Plant> createPlant({
    required String name,
    SlotRef sensor = const SlotRef(),
    SlotRef pump = const SlotRef(),
    String notes = '',
  });
  Future<Plant> updatePlant(
    String id, {
    String? name,
    String? notes,
    SlotRef? sensor,
    SlotRef? pump,
  });
  Future<void> deletePlant(String id);
  Future<List<Reading>> readings(String plantId, ChartRange range);

  Future<List<Command>> commands(String plantId);
  Future<Command> waterNow(String plantId, int seconds);
  Future<void> cancelCommand(String commandId);

  Future<List<Rule>> rules(String plantId);
  Future<Rule> saveRule(Rule rule);
  Future<void> deleteRule(Rule rule);
  Future<List<RuleExecution>> ruleExecutions(String plantId, String ruleId);

  // ---- devices -------------------------------------------------------------------------------
  Future<List<Device>> devices();
  Future<DeviceConfig> deviceConfig(String deviceId);
  Future<Board?> board(String name);

  /// Sends a new configuration; `baseRev` is the revision it was edited from (`conflict` otherwise).
  Future<int> saveDeviceConfig(
    String deviceId,
    int baseRev,
    DeviceConfigBody config,
  );
  Future<Device> renameDevice(String deviceId, String name);

  /// Needs [reauth]. A device that cannot be reached is removed with [force].
  Future<void> deleteDevice(String deviceId, {bool force = false});
  Future<void> deviceAction(String deviceId, DeviceAction action);

  /// Admin: sets the battery correction from a multimeter reading in millivolts (the hub refuses more than 10 % off).
  Future<void> calibrateBattery(String deviceId, int measuredMv);

  /// Stored battery reports of a device for the chart.
  Future<List<BatteryPoint>> batteryHistory(String deviceId, ChartRange range);
  Future<List<Map<String, Object?>>> deviceEvents(String deviceId);

  Future<JoinState> joinState();
  Future<JoinState> openJoin({String? installCode, int seconds = 120});
  Future<void> closeJoin();

  // ---- alerts --------------------------------------------------------------------------------
  Future<List<Alert>> alerts();
  Future<void> acknowledgeAlert(String alertId);

  /// Live updates (SSE stream on the real backend).
  Stream<LiveEvent> events();
}
