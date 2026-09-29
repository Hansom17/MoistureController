import '../models.dart';

/// Everything the app reads from or writes to the cloud backend.
///
/// Screens never use this directly — only through providers (App_Specs §3).
/// Implementations: [FakeMoistureRepository] (no backend) and
/// [ApiMoistureRepository] (the cloud backend's REST + SSE API).
abstract interface class MoistureRepository {
  Future<List<Household>> households();

  Future<List<Plant>> plants(String householdId);
  Future<List<Reading>> readings(
    String householdId,
    String plantId,
    ChartRange range,
  );

  Future<List<Command>> commands(String householdId, String plantId);
  Future<Command> waterNow(String householdId, String plantId, int seconds);
  Future<void> cancelCommand(String householdId, String commandId);

  Future<List<Rule>> rules(String householdId, String plantId);
  Future<Rule> saveRule(String householdId, Rule rule);
  Future<void> deleteRule(String householdId, Rule rule);

  Future<List<Device>> devices(String householdId);
  Future<void> deviceAction(
    String householdId,
    String deviceId,
    DeviceAction action,
  );

  Future<List<Alert>> alerts(String householdId);
  Future<void> acknowledgeAlert(String householdId, String alertId);

  /// Live updates for one household (SSE stream on the real backend).
  Stream<LiveEvent> events(String householdId);
}
