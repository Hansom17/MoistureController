// Hand-written models mirroring the backend API.
//
// Replace with the generated client (`contracts/api.yaml`, App_Specs §2) once
// the backend publishes its spec; repositories keep the same shapes.

enum Role { viewer, member, admin, owner }

class Household {
  const Household({
    required this.id,
    required this.name,
    required this.timezone,
    required this.role,
    this.hub,
  });

  final String id;
  final String name;
  final String timezone;
  final Role role;

  /// Null when the household has no hub.
  final HubStatus? hub;

  Household copyWith({Role? role, HubStatus? hub}) => Household(
    id: id,
    name: name,
    timezone: timezone,
    role: role ?? this.role,
    hub: hub ?? this.hub,
  );
}

class HubStatus {
  const HubStatus({required this.online, this.offlineSince, this.version});

  final bool online;
  final DateTime? offlineSince;
  final String? version;
}

/// Device connectivity as shown in the UI (App_Specs §7).
enum DeviceState { online, sleeping, late, offline }

enum ConfigSync { inSync, pending, rejected }

class Device {
  const Device({
    required this.id,
    required this.name,
    required this.board,
    required this.firmware,
    required this.batteryPercent,
    required this.rssi,
    required this.state,
    required this.lastSeen,
    required this.nextExpectedAt,
    required this.wakeIntervalS,
    required this.configSync,
    required this.configRev,
    required this.slots,
    this.configError,
  });

  final String id;
  final String name;
  final String board;
  final String firmware;
  final int batteryPercent;
  final int rssi;
  final DeviceState state;
  final DateTime lastSeen;
  final DateTime nextExpectedAt;
  final int wakeIntervalS;
  final ConfigSync configSync;
  final int configRev;
  final String? configError;
  final List<Slot> slots;

  Device copyWith({
    DeviceState? state,
    DateTime? lastSeen,
    DateTime? nextExpectedAt,
    int? batteryPercent,
  }) => Device(
    id: id,
    name: name,
    board: board,
    firmware: firmware,
    batteryPercent: batteryPercent ?? this.batteryPercent,
    rssi: rssi,
    state: state ?? this.state,
    lastSeen: lastSeen ?? this.lastSeen,
    nextExpectedAt: nextExpectedAt ?? this.nextExpectedAt,
    wakeIntervalS: wakeIntervalS,
    configSync: configSync,
    configRev: configRev,
    configError: configError,
    slots: slots,
  );
}

class Slot {
  const Slot({
    required this.index,
    required this.module,
    required this.pin,
    this.maxRunS,
  });

  final int index;

  /// Module type from the contract's module list, e.g. `capacitive_moisture`.
  final String module;
  final int pin;

  /// Pump hard limit; only for actuator slots.
  final int? maxRunS;
}

/// One-shot device actions, delivered on the next wake.
enum DeviceAction { identify, serviceMode, reboot }

enum Trend { falling, steady, rising }

class Plant {
  const Plant({
    required this.id,
    required this.name,
    required this.deviceId,
    required this.moisturePercent,
    required this.trend,
    required this.lastReadingAt,
    required this.maxRunS,
  });

  final String id;
  final String name;
  final String deviceId;

  /// Null until the first reading arrives.
  final double? moisturePercent;
  final Trend trend;
  final DateTime? lastReadingAt;

  /// Pump limit for "Water now", from the pump slot's `max_run_s`; 0 = no pump.
  final int maxRunS;

  bool get hasPump => maxRunS > 0;

  Plant copyWith({
    double? moisturePercent,
    Trend? trend,
    DateTime? lastReadingAt,
  }) => Plant(
    id: id,
    name: name,
    deviceId: deviceId,
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

/// Chart range with its bucket size (App_Specs §4, plant detail).
enum ChartRange {
  day(Duration(hours: 24), Duration(minutes: 30)),
  week(Duration(days: 7), Duration(hours: 3)),
  month(Duration(days: 30), Duration(hours: 12)),
  year(Duration(days: 365), Duration(days: 7));

  const ChartRange(this.span, this.bucket);

  final Duration span;
  final Duration bucket;
}

enum CommandState {
  queued,
  delivered,
  running,
  done,
  failed,
  expired,
  cancelled,
}

extension CommandStateX on CommandState {
  bool get isFinal => switch (this) {
    CommandState.done ||
    CommandState.failed ||
    CommandState.expired ||
    CommandState.cancelled => true,
    _ => false,
  };
}

class Command {
  const Command({
    required this.id,
    required this.plantId,
    required this.seconds,
    required this.state,
    required this.createdAt,
    required this.expectedAt,
    this.runningUntil,
    this.finishedAt,
    this.failureReason,
    this.origin = CommandOrigin.user,
  });

  final String id;
  final String plantId;
  final int seconds;
  final CommandState state;
  final DateTime createdAt;

  /// When the device is expected to pick the command up (`next_expected_at`).
  final DateTime expectedAt;
  final DateTime? runningUntil;
  final DateTime? finishedAt;
  final String? failureReason;
  final CommandOrigin origin;

  Command copyWith({
    CommandState? state,
    DateTime? runningUntil,
    DateTime? finishedAt,
  }) => Command(
    id: id,
    plantId: plantId,
    seconds: seconds,
    state: state ?? this.state,
    createdAt: createdAt,
    expectedAt: expectedAt,
    runningUntil: runningUntil ?? this.runningUntil,
    finishedAt: finishedAt ?? this.finishedAt,
    failureReason: failureReason,
    origin: origin,
  );
}

enum CommandOrigin { user, cloudRule, hubRule }

class Rule {
  const Rule({
    required this.id,
    required this.plantId,
    required this.belowPercent,
    required this.waterSeconds,
    required this.minIntervalHours,
    required this.enabled,
  });

  final String id;
  final String plantId;
  final int belowPercent;
  final int waterSeconds;
  final int minIntervalHours;
  final bool enabled;

  Rule copyWith({
    int? belowPercent,
    int? waterSeconds,
    int? minIntervalHours,
    bool? enabled,
  }) => Rule(
    id: id,
    plantId: plantId,
    belowPercent: belowPercent ?? this.belowPercent,
    waterSeconds: waterSeconds ?? this.waterSeconds,
    minIntervalHours: minIntervalHours ?? this.minIntervalHours,
    enabled: enabled ?? this.enabled,
  );
}

enum AlertKind {
  deviceOffline,
  batteryLow,
  sensorSuspect,
  commandFailed,
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
    this.kindName,
  });

  final String id;
  final AlertKind kind;

  /// Backend kind (e.g. `config_rejected`) for [AlertKind.other].
  final String? kindName;

  /// Plant or device name the alert is about.
  final String subject;
  final DateTime createdAt;
  final bool open;
  final DateTime? acknowledgedAt;

  Alert acknowledge(DateTime at) => Alert(
    id: id,
    kind: kind,
    subject: subject,
    createdAt: createdAt,
    open: false,
    acknowledgedAt: at,
    kindName: kindName,
  );
}

/// Server-sent event kinds (App_Specs §6.2).
enum LiveEventKind {
  reading,
  command,
  device,
  config,
  alert,
  hub,
  household,
  rule,
  resync,
}

class LiveEvent {
  const LiveEvent(this.kind, {this.entityId});

  final LiveEventKind kind;
  final String? entityId;
}
