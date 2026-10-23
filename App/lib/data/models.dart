// Hand-written models mirroring the gateway's `api` (Gateway/specs.md Part A §6).
//
// Replace with a generated client once the api publishes its OpenAPI document; repositories keep
// the same shapes.

enum Role { viewer, member, admin, owner }

/// A person with an account on this gateway (`GET /me`, `GET /users`).
class AppUser {
  const AppUser({
    required this.id,
    required this.username,
    required this.displayName,
    required this.role,
    this.disabled = false,
    this.createdAt,
  });

  final String id;
  final String username;
  final String displayName;
  final Role role;
  final bool disabled;
  final DateTime? createdAt;

  AppUser copyWith({Role? role, String? displayName, bool? disabled}) => AppUser(
    id: id,
    username: username,
    displayName: displayName ?? this.displayName,
    role: role ?? this.role,
    disabled: disabled ?? this.disabled,
    createdAt: createdAt,
  );
}

/// What `GET /meta` says before anyone is signed in.
class GatewayMeta {
  const GatewayMeta({
    required this.name,
    required this.setupRequired,
    required this.hubOnline,
    this.hubCompatible = true,
    this.version,
  });

  final String name;
  final bool setupRequired;
  final bool hubOnline;
  final bool hubCompatible;
  final String? version;
}

/// A login: the token the app stores and the user it belongs to.
class Session {
  const Session({required this.token, required this.user});

  final String token;
  final AppUser user;
}

/// Installation settings (`GET /installation`, owner changes them).
class Installation {
  const Installation({
    required this.name,
    required this.timezone,
    this.batteryLowMv = 3600,
    this.batteryCriticalMv = 3400,
    this.telegramConfigured = false,
  });

  final String name;
  final String timezone;
  final int batteryLowMv;
  final int batteryCriticalMv;
  final bool telegramConfigured;
}

/// `GET /status`: what runs on the gateway box.
class GatewayStatus {
  const GatewayStatus({
    required this.hubOnline,
    required this.zigbee,
    this.coordinator,
    this.hubVersion,
    this.apiVersion,
    this.clockSynced,
    this.dbSizeBytes,
  });

  final bool hubOnline;

  /// Zigbee2MQTT: `online`, `offline` or `unknown`.
  final String zigbee;
  final String? coordinator;
  final String? hubVersion;
  final String? apiVersion;
  final bool? clockSynced;
  final int? dbSizeBytes;

  bool get zigbeeDown => hubOnline && zigbee == 'offline';
}

/// Device connectivity and lifecycle as shown in the UI (Gateway/specs.md section 11).
enum DeviceStatus {
  joining,
  joinFailed,
  unsupported,
  ready,
  online,
  late,
  offline,
  safeMode,
}

enum ConfigSync { inSync, pending, rejected }

/// One slot of a device's configuration: what is plugged into which port.
class SlotConfig {
  const SlotConfig({
    required this.slot,
    required this.module,
    required this.port,
    this.calDry = 3000,
    this.calWet = 1200,
    this.samples = 16,
    this.maxRunS = 60,
    this.minPauseS = 600,
    this.activeHigh = true,
  });

  final int slot;

  /// `moisture` or `pump`.
  final String module;

  /// Logical port of the board, `P1`...
  final String port;
  final int calDry;
  final int calWet;
  final int samples;
  final int maxRunS;
  final int minPauseS;
  final bool activeHigh;

  bool get isPump => module == 'pump';

  SlotConfig copyWith({
    int? slot,
    String? module,
    String? port,
    int? calDry,
    int? calWet,
    int? samples,
    int? maxRunS,
    int? minPauseS,
    bool? activeHigh,
  }) => SlotConfig(
    slot: slot ?? this.slot,
    module: module ?? this.module,
    port: port ?? this.port,
    calDry: calDry ?? this.calDry,
    calWet: calWet ?? this.calWet,
    samples: samples ?? this.samples,
    maxRunS: maxRunS ?? this.maxRunS,
    minPauseS: minPauseS ?? this.minPauseS,
    activeHigh: activeHigh ?? this.activeHigh,
  );
}

/// A whole device configuration revision.
class DeviceConfigBody {
  const DeviceConfigBody({
    this.rev = 0,
    this.reportIntervalS = 300,
    this.fastReportIntervalS = 30,
    this.fastReportHoldS = 120,
    this.battLowMv = 3500,
    this.slots = const [],
  });

  final int rev;
  final int reportIntervalS;
  final int fastReportIntervalS;
  final int fastReportHoldS;
  final int battLowMv;
  final List<SlotConfig> slots;

  DeviceConfigBody copyWith({
    int? reportIntervalS,
    int? fastReportIntervalS,
    int? fastReportHoldS,
    List<SlotConfig>? slots,
  }) => DeviceConfigBody(
    rev: rev,
    reportIntervalS: reportIntervalS ?? this.reportIntervalS,
    fastReportIntervalS: fastReportIntervalS ?? this.fastReportIntervalS,
    fastReportHoldS: fastReportHoldS ?? this.fastReportHoldS,
    battLowMv: battLowMv,
    slots: slots ?? this.slots,
  );
}

/// `GET /devices/{d}/config`: desired and reported configuration and how they relate.
class DeviceConfig {
  const DeviceConfig({
    required this.desiredRev,
    required this.reportedRev,
    required this.sync,
    this.desired,
    this.reported,
    this.error,
    this.board,
  });

  final int desiredRev;
  final int? reportedRev;
  final ConfigSync sync;
  final DeviceConfigBody? desired;
  final DeviceConfigBody? reported;
  final String? error;
  final String? board;
}

/// A logical port of a board revision and what it can be (`GET /meta/boards/{board}`).
class BoardPort {
  const BoardPort({required this.id, required this.roles});

  final String id;
  final List<String> roles;
}

class Board {
  const Board({required this.name, required this.ports});

  final String name;
  final List<BoardPort> ports;
}

/// Battery state of a module (PlantModule/specs.md 6.1): `absent` means no cell is connected (USB only).
enum BatteryState { absent, ok, low, critical }

/// What the hub says about the cell of a device (`battery` in the device snapshot). The percentage is an estimate
/// and null when the last report is old.
class Battery {
  const Battery({
    required this.state,
    this.mv = 0,
    this.percent,
    this.calibrated = false,
    this.calPermille = 1000,
  });

  final BatteryState state;
  final int mv;
  final int? percent;
  final bool calibrated;
  final int calPermille;

  bool get present => state != BatteryState.absent && mv > 0;
  double get volts => mv / 1000;
}

/// One stored battery report for the chart.
class BatteryPoint {
  const BatteryPoint(this.at, this.mv);

  final DateTime at;
  final int mv;
}

class Device {
  const Device({
    required this.id,
    required this.name,
    required this.status,
    required this.configSync,
    this.model,
    this.board,
    this.firmware,
    this.safeReason,
    this.lastSeen,
    this.linkQuality,
    this.voltageMv,
    this.battery,
    this.desiredRev = 0,
    this.reportedRev,
    this.configError,
    this.slots = const [],
    this.diagnostics = const {},
  });

  final String id;
  final String name;
  final DeviceStatus status;
  final ConfigSync configSync;
  final String? model;
  final String? board;
  final String? firmware;
  final String? safeReason;
  final DateTime? lastSeen;

  /// Zigbee link quality 0..255.
  final int? linkQuality;
  final int? voltageMv;

  /// Null for a device the hub sends no battery object for.
  final Battery? battery;
  final int desiredRev;
  final int? reportedRev;
  final String? configError;

  /// The slots of the configuration the device runs.
  final List<SlotConfig> slots;

  /// uptime_s, boot_reason, reset_count, rejoin_count, last_error, free_heap
  final Map<String, Object?> diagnostics;

  bool get reachable =>
      status == DeviceStatus.online ||
      status == DeviceStatus.late ||
      status == DeviceStatus.ready;

  bool get isNew =>
      status == DeviceStatus.joining ||
      status == DeviceStatus.joinFailed ||
      status == DeviceStatus.unsupported;

  Device copyWith({String? name, DeviceStatus? status, DateTime? lastSeen}) =>
      Device(
        id: id,
        name: name ?? this.name,
        status: status ?? this.status,
        configSync: configSync,
        model: model,
        board: board,
        firmware: firmware,
        safeReason: safeReason,
        lastSeen: lastSeen ?? this.lastSeen,
        linkQuality: linkQuality,
        voltageMv: voltageMv,
        battery: battery,
        desiredRev: desiredRev,
        reportedRev: reportedRev,
        configError: configError,
        slots: slots,
        diagnostics: diagnostics,
      );
}

/// The join window (`GET /devices/join`).
class JoinState {
  const JoinState({
    this.open = false,
    this.endsAt,
    this.deviceIds = const [],
    this.error,
  });

  final bool open;
  final DateTime? endsAt;

  /// Devices that joined during the window.
  final List<String> deviceIds;
  final String? error;
}

/// One-shot device actions.
enum DeviceAction { identify, reboot, clearSafeMode }

/// Where a plant's sensor or pump is plugged in.
class SlotRef {
  const SlotRef({this.deviceId, this.slot});

  final String? deviceId;
  final int? slot;

  bool get isSet => deviceId != null && slot != null;
}

enum Trend { falling, steady, rising }

class Plant {
  const Plant({
    required this.id,
    required this.name,
    required this.moisturePercent,
    required this.trend,
    required this.lastReadingAt,
    required this.maxRunS,
    this.notes = '',
    this.sensor = const SlotRef(),
    this.pump = const SlotRef(),
  });

  final String id;
  final String name;
  final String notes;
  final SlotRef sensor;
  final SlotRef pump;

  /// Null until the first reading arrives.
  final double? moisturePercent;
  final Trend trend;
  final DateTime? lastReadingAt;

  /// Pump limit for "Water now", from the pump slot's `max_run_s`; 0 = no pump.
  final int maxRunS;

  bool get hasPump => maxRunS > 0;

  /// The device the plant's readings come from (or its pump when it has no sensor).
  String? get deviceId => sensor.deviceId ?? pump.deviceId;

  Plant copyWith({
    double? moisturePercent,
    Trend? trend,
    DateTime? lastReadingAt,
  }) => Plant(
    id: id,
    name: name,
    notes: notes,
    sensor: sensor,
    pump: pump,
    moisturePercent: moisturePercent ?? this.moisturePercent,
    trend: trend ?? this.trend,
    lastReadingAt: lastReadingAt ?? this.lastReadingAt,
    maxRunS: maxRunS,
  );
}

class Reading {
  const Reading(this.at, this.moisturePercent);

  final DateTime at;
  final double moisturePercent;
}

/// Chart range with its bucket size (App/specs.md Part A §4, plant detail).
enum ChartRange {
  day(Duration(hours: 24), Duration(minutes: 30)),
  week(Duration(days: 7), Duration(hours: 3)),
  month(Duration(days: 30), Duration(hours: 12)),
  year(Duration(days: 365), Duration(days: 7));

  const ChartRange(this.span, this.bucket);

  final Duration span;
  final Duration bucket;
}

enum CommandState { queued, running, done, failed, expired, cancelled }

extension CommandStateX on CommandState {
  bool get isFinal => switch (this) {
    CommandState.done ||
    CommandState.failed ||
    CommandState.expired ||
    CommandState.cancelled => true,
    _ => false,
  };
}

/// Who started a command: a person in the app or a rule on the gateway.
enum CommandOrigin { user, rule }

class Command {
  const Command({
    required this.id,
    required this.plantId,
    required this.deviceId,
    required this.seconds,
    required this.state,
    required this.createdAt,
    this.cancelling = false,
    this.sent = false,
    this.expiresAt,
    this.runningUntil,
    this.finishedAt,
    this.failureReason,
    this.origin = CommandOrigin.user,
  });

  final String id;
  final String plantId;
  final String deviceId;
  final int seconds;
  final CommandState state;
  final DateTime createdAt;

  /// A cancel was requested and the module has not confirmed yet.
  final bool cancelling;

  /// Handed to Zigbee already (otherwise a queued command is waiting for the device).
  final bool sent;

  /// A queued command that was not delivered by then expires.
  final DateTime? expiresAt;
  final DateTime? runningUntil;
  final DateTime? finishedAt;
  final String? failureReason;
  final CommandOrigin origin;

  Command copyWith({
    CommandState? state,
    DateTime? runningUntil,
    DateTime? finishedAt,
    bool? cancelling,
  }) => Command(
    id: id,
    plantId: plantId,
    deviceId: deviceId,
    seconds: seconds,
    state: state ?? this.state,
    createdAt: createdAt,
    cancelling: cancelling ?? this.cancelling,
    sent: sent,
    expiresAt: expiresAt,
    runningUntil: runningUntil ?? this.runningUntil,
    finishedAt: finishedAt ?? this.finishedAt,
    failureReason: failureReason,
    origin: origin,
  );
}

class Rule {
  const Rule({
    required this.id,
    required this.plantId,
    required this.belowPercent,
    required this.waterSeconds,
    required this.cooldownS,
    required this.maxPerDay,
    required this.enabled,
    this.quietFrom,
    this.quietTo,
    this.notifyChannels = const ['app'],
    this.notifyOn = const ['failed'],
  });

  final String id;
  final String plantId;
  final int belowPercent;
  final int waterSeconds;
  final int cooldownS;
  final int maxPerDay;
  final bool enabled;

  /// "HH:MM" in the installation's timezone, or null for no quiet hours.
  final String? quietFrom;
  final String? quietTo;
  final List<String> notifyChannels;
  final List<String> notifyOn;

  int get cooldownHours => (cooldownS / 3600).round();

  Rule copyWith({
    int? belowPercent,
    int? waterSeconds,
    int? cooldownS,
    int? maxPerDay,
    bool? enabled,
    String? quietFrom,
    String? quietTo,
    bool clearQuiet = false,
    List<String>? notifyChannels,
    List<String>? notifyOn,
  }) => Rule(
    id: id,
    plantId: plantId,
    belowPercent: belowPercent ?? this.belowPercent,
    waterSeconds: waterSeconds ?? this.waterSeconds,
    cooldownS: cooldownS ?? this.cooldownS,
    maxPerDay: maxPerDay ?? this.maxPerDay,
    enabled: enabled ?? this.enabled,
    quietFrom: clearQuiet ? null : quietFrom ?? this.quietFrom,
    quietTo: clearQuiet ? null : quietTo ?? this.quietTo,
    notifyChannels: notifyChannels ?? this.notifyChannels,
    notifyOn: notifyOn ?? this.notifyOn,
  );
}

/// One decision of a rule ("why did / didn't it water?").
class RuleExecution {
  const RuleExecution({
    required this.at,
    required this.decision,
    this.skipReason,
    this.commandId,
  });

  final DateTime at;

  /// `water` or `skip`.
  final String decision;
  final String? skipReason;
  final String? commandId;
}

enum AlertKind {
  deviceOffline,
  batteryLow,
  batteryCritical,
  sensorSuspect,
  commandFailed,
  safeMode,
  zigbeeOffline,
  other,
}

class Alert {
  const Alert({
    required this.id,
    required this.kind,
    required this.subject,
    required this.createdAt,
    required this.open,
    this.acknowledgedAt,
    this.acknowledgedBy,
    this.kindName,
    this.critical = false,
  });

  final String id;
  final AlertKind kind;

  /// Backend kind (e.g. `config_rejected`) for [AlertKind.other].
  final String? kindName;

  /// Plant or device name the alert is about.
  final String subject;
  final DateTime createdAt;
  final bool open;
  final bool critical;
  final DateTime? acknowledgedAt;
  final String? acknowledgedBy;

  Alert acknowledge(DateTime at, {String? by}) => Alert(
    id: id,
    kind: kind,
    subject: subject,
    createdAt: createdAt,
    open: false,
    acknowledgedAt: at,
    acknowledgedBy: by,
    kindName: kindName,
    critical: critical,
  );
}

// ---- users, invites, tokens --------------------------------------------------------------------

class Invite {
  const Invite({
    required this.id,
    required this.role,
    required this.status,
    required this.expiresAt,
  });

  final String id;
  final Role role;

  /// open · used · revoked · expired
  final String status;
  final DateTime expiresAt;
}

/// An invite right after it was created: the code is shown once.
class CreatedInvite {
  const CreatedInvite({required this.invite, required this.code});

  final Invite invite;
  final String code;

  /// The link to give to the person: `<origin>/join#c=<code>` (the fragment never leaves the browser).
  String link(String origin) => '$origin/join#c=$code';
}

class InvitePreview {
  const InvitePreview({required this.role, required this.installation});

  final Role role;
  final String installation;
}

/// A login of this user on some device ("Philipp's iPhone").
class TokenInfo {
  const TokenInfo({
    required this.id,
    required this.name,
    required this.createdAt,
    required this.current,
    this.lastUsedAt,
  });

  final String id;
  final String name;
  final DateTime createdAt;
  final DateTime? lastUsedAt;
  final bool current;
}

class AuditEntry {
  const AuditEntry({
    required this.id,
    required this.actor,
    required this.action,
    required this.at,
    this.detail,
  });

  final int id;
  final String actor;
  final String action;
  final DateTime at;
  final Map<String, Object?>? detail;
}

/// Server-sent event kinds (Gateway/specs.md 3.4 and 6.1).
enum LiveEventKind {
  reading,
  command,
  device,
  config,
  plant,
  rule,
  alert,
  installation,
  join,
  notification,
  status,
  resync,
}

class LiveEvent {
  const LiveEvent(this.kind, {this.entityId, this.text});

  final LiveEventKind kind;
  final String? entityId;

  /// For notifications: the message.
  final String? text;
}
