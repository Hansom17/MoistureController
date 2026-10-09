import 'dart:async';
import 'dart:math';

import '../api_problem.dart';
import '../models.dart';
import 'moisture_repository.dart';

/// In-memory backend for development without a gateway.
///
/// Mirrors the api's behaviour closely enough to exercise the UI: sign-in and roles, pump limits,
/// commands that go queued → running → done over a few seconds with live events (or stay queued
/// while a device is offline), configuration revisions that are pending until the "device"
/// confirms, and a join window that brings a new device in.
class FakeMoistureRepository implements MoistureRepository {
  FakeMoistureRepository({
    DateTime Function()? clock,
    this.latency = const Duration(milliseconds: 250),
    this.deviceDelay = const Duration(seconds: 2),
    bool setupRequired = false,
    Role role = Role.owner,
  }) : _clock = clock ?? DateTime.now,
       _setupRequired = setupRequired,
       _role = role {
    _seed();
  }

  final DateTime Function() _clock;

  /// Simulated network round trip.
  final Duration latency;

  /// Time a device needs to answer (acknowledge a command, apply a configuration).
  final Duration deviceDelay;

  bool _setupRequired;
  Role _role;
  String? _token;
  var _meId = 'u-demo';
  var _proofUntil = DateTime.fromMillisecondsSinceEpoch(0);
  var _installation = const Installation(name: 'Home', timezone: 'Europe/Berlin');
  var _join = const JoinState();
  var _nextId = 100; // above the ids of the seed data
  var _zigbee = 'online';

  final _users = <AppUser>[];
  final _passwords = <String, String>{};
  final _tokens = <TokenInfo>[];
  final _invites = <Invite>[];
  final _inviteCodes = <String, String>{};
  final _audit = <AuditEntry>[];
  final _plants = <Plant>[];
  final _devices = <Device>[];
  final _configs = <String, DeviceConfigBody>{};
  final _commands = <Command>[];
  final _rules = <Rule>[];
  final _alerts = <Alert>[];
  final _curves = <String, _Curve>{};
  final _stream = StreamController<LiveEvent>.broadcast();
  final _timers = <Timer>[];

  /// Dev-only: lets the settings screen switch the demo role.
  void setRole(Role role) {
    _role = role;
    final i = _users.indexWhere((u) => u.id == _meId);
    _users[i] = _users[i].copyWith(role: role);
    _emit(const LiveEvent(LiveEventKind.installation));
  }

  Role get role => _role;

  /// Dev-only: Zigbee2MQTT goes down or comes back.
  void setZigbee(String state) {
    _zigbee = state;
    _emit(const LiveEvent(LiveEventKind.status));
  }

  void dispose() {
    for (final t in _timers) {
      t.cancel();
    }
    _stream.close();
  }

  void _after(Duration d, void Function() f) => _timers.add(Timer(d, f));

  // ---- sign-in ------------------------------------------------------------------------------

  @override
  Future<GatewayMeta> meta() => _delay(
    () => GatewayMeta(
      name: _installation.name,
      setupRequired: _setupRequired,
      hubOnline: true,
      version: 'fake',
    ),
  );

  Session _newSession(AppUser user, String deviceName) {
    final token = 'tok-${_nextId++}';
    _tokens.add(
      TokenInfo(
        id: token,
        name: deviceName.isEmpty ? 'this device' : deviceName,
        createdAt: _clock(),
        lastUsedAt: _clock(),
        current: true,
      ),
    );
    _token = token;
    return Session(token: token, user: user);
  }

  @override
  Future<Session> setup({
    required String setupCode,
    required String name,
    required String timezone,
    required String username,
    required String password,
    String displayName = '',
  }) => _delay(() {
    if (!_setupRequired) throw const ApiProblem(ApiProblem.alreadySetUp, status: 409);
    if (setupCode.trim().toUpperCase() != 'DEMOCODE') {
      throw const ApiProblem(ApiProblem.invalidSetupCode, status: 403);
    }
    _installation = Installation(name: name, timezone: timezone);
    final user = AppUser(
      id: 'u-owner',
      username: username,
      displayName: displayName.isEmpty ? username : displayName,
      role: Role.owner,
      createdAt: _clock(),
    );
    _users
      ..clear()
      ..add(user);
    _meId = user.id;
    _passwords[username] = password;
    _role = Role.owner;
    _setupRequired = false;
    return _newSession(user, 'setup');
  });

  @override
  Future<Session> login({
    required String username,
    required String password,
    String deviceName = '',
  }) => _delay(() {
    final user = _users.where((u) => u.username == username.toLowerCase()).firstOrNull;
    if (user == null || user.disabled || _passwords[user.username] != password) {
      throw const ApiProblem(ApiProblem.invalidCredentials, status: 401);
    }
    _role = user.role;
    _meId = user.id;
    return _newSession(user, deviceName);
  });

  @override
  Future<InvitePreview> previewInvite(String code) => _delay(() {
    final invite = _openInvite(code);
    return InvitePreview(role: invite.role, installation: _installation.name);
  });

  Invite _openInvite(String code) {
    final id = _inviteCodes[code.trim().toUpperCase()];
    final invite = _invites.where((i) => i.id == id && i.status == 'open').firstOrNull;
    if (invite == null) throw const ApiProblem(ApiProblem.invalidInvite, status: 404);
    return invite;
  }

  @override
  Future<Session> acceptInvite({
    required String code,
    required String username,
    required String password,
    String displayName = '',
    String deviceName = '',
  }) => _delay(() {
    final invite = _openInvite(code);
    if (_users.any((u) => u.username == username.toLowerCase())) {
      throw const ApiProblem(ApiProblem.conflict, status: 409);
    }
    final user = AppUser(
      id: 'u${_nextId++}',
      username: username.toLowerCase(),
      displayName: displayName.isEmpty ? username : displayName,
      role: invite.role,
      createdAt: _clock(),
    );
    _users.add(user);
    _passwords[user.username] = password;
    _invites[_invites.indexOf(invite)] = Invite(
      id: invite.id,
      role: invite.role,
      status: 'used',
      expiresAt: invite.expiresAt,
    );
    _role = user.role;
    _meId = user.id;
    return _newSession(user, deviceName);
  });

  @override
  void useToken(String? token) => _token = token;

  AppUser get _me => _users.firstWhere((u) => u.id == _meId);

  @override
  Future<AppUser> me() => _delay(() {
    if (_token == null) throw const ApiProblem(ApiProblem.unauthorized, status: 401);
    return _me.copyWith(role: _role);
  });

  @override
  Future<void> logout() => _delay(() {
    _tokens.removeWhere((t) => t.id == _token);
    _token = null;
  });

  @override
  Future<AppUser> updateMe({String? displayName}) => _delay(() {
    final i = _users.indexWhere((u) => u.id == _meId);
    _users[i] = _users[i].copyWith(displayName: displayName);
    return _users[i];
  });

  @override
  Future<void> changePassword({required String currentPassword, required String newPassword}) =>
      _delay(() {
        if (_passwords[_me.username] != currentPassword) {
          throw const ApiProblem(ApiProblem.invalidCredentials, status: 401);
        }
        _passwords[_me.username] = newPassword;
        _tokens.removeWhere((t) => !t.current);
      });

  @override
  Future<void> reauth(String password) => _delay(() {
    if (_passwords[_me.username] != password) {
      throw const ApiProblem(ApiProblem.invalidCredentials, status: 401);
    }
    _proofUntil = _clock().add(const Duration(minutes: 5));
  });

  void _needProof() {
    if (_clock().isAfter(_proofUntil)) {
      throw const ApiProblem(ApiProblem.reauthRequired, status: 401);
    }
  }

  // ---- tokens, users, invites, audit ----------------------------------------------------------

  @override
  Future<List<TokenInfo>> tokens() => _delay(() => List.of(_tokens));

  @override
  Future<void> revokeToken(String id) => _delay(() => _tokens.removeWhere((t) => t.id == id));

  @override
  Future<List<AppUser>> users() => _delay(() => List.of(_users));

  @override
  Future<AppUser> updateUser(String id, {Role? role, String? displayName, bool? disabled}) =>
      _delay(() {
        _require(Role.admin);
        final i = _users.indexWhere((u) => u.id == id);
        if (i < 0) throw const ApiProblem(ApiProblem.notFound, status: 404);
        if (_users[i].role == Role.owner) throw const ApiProblem(ApiProblem.forbidden, status: 403);
        if (_role != Role.owner && (_users[i].role == Role.admin || role == Role.admin)) {
          throw const ApiProblem(ApiProblem.forbidden, status: 403);
        }
        if (role == Role.admin || _users[i].role == Role.admin) _needProof();
        _users[i] = _users[i].copyWith(role: role, displayName: displayName, disabled: disabled);
        _log('user_updated');
        return _users[i];
      });

  @override
  Future<void> deleteUser(String id) => _delay(() {
    _require(Role.admin);
    final u = _users.firstWhere((u) => u.id == id);
    if (u.role == Role.owner) throw const ApiProblem(ApiProblem.forbidden, status: 403);
    if (u.role == Role.admin) _needProof();
    _users.remove(u);
    _log('user_removed');
  });

  @override
  Future<void> transferOwnership(String userId) => _delay(() {
    _require(Role.owner);
    _needProof();
    for (var i = 0; i < _users.length; i++) {
      if (_users[i].role == Role.owner) _users[i] = _users[i].copyWith(role: Role.admin);
      if (_users[i].id == userId) _users[i] = _users[i].copyWith(role: Role.owner);
    }
    _role = Role.admin;
  });

  @override
  Future<List<Invite>> invites() => _delay(() {
    _require(Role.admin);
    return List.of(_invites);
  });

  @override
  Future<CreatedInvite> createInvite(Role role, {Duration? expiresIn}) => _delay(() {
    _require(Role.admin);
    final id = 'i${_nextId++}';
    final code = 'CODE${id.toUpperCase()}ABCDEFGH';
    final invite = Invite(
      id: id,
      role: role,
      status: 'open',
      expiresAt: _clock().add(expiresIn ?? const Duration(hours: 48)),
    );
    _invites.insert(0, invite);
    _inviteCodes[code] = id;
    _log('invite_created');
    return CreatedInvite(invite: invite, code: code);
  });

  @override
  Future<void> revokeInvite(String id) => _delay(() {
    final i = _invites.indexWhere((x) => x.id == id);
    final v = _invites[i];
    _invites[i] = Invite(id: v.id, role: v.role, status: 'revoked', expiresAt: v.expiresAt);
  });

  @override
  Future<List<AuditEntry>> audit({int? before, int limit = 100}) => _delay(() {
    _require(Role.admin);
    return [
      for (final a in _audit.reversed)
        if (before == null || a.id < before) a,
    ].take(limit).toList();
  });

  void _log(String action) =>
      _audit.add(AuditEntry(id: _audit.length + 1, actor: _me.id, action: action, at: _clock()));

  // ---- installation and gateway -----------------------------------------------------------------

  @override
  Future<Installation> installation() => _delay(() => _installation);

  @override
  Future<Installation> updateInstallation({
    String? name,
    String? timezone,
    int? batteryLowMv,
    String? telegramToken,
    String? telegramChatId,
  }) => _delay(() {
    _require(Role.owner);
    _installation = Installation(
      name: name ?? _installation.name,
      timezone: timezone ?? _installation.timezone,
      batteryLowMv: batteryLowMv ?? _installation.batteryLowMv,
      telegramConfigured:
          _installation.telegramConfigured || (telegramToken != null && telegramChatId != null),
    );
    _emit(const LiveEvent(LiveEventKind.installation));
    return _installation;
  });

  @override
  Future<GatewayStatus> gatewayStatus() => _delay(
    () => GatewayStatus(
      hubOnline: true,
      zigbee: _zigbee,
      coordinator: 'SONOFF Dongle Plus MG24',
      hubVersion: '0.1.0',
      apiVersion: '0.1.0',
      clockSynced: true,
      dbSizeBytes: 1536000,
    ),
  );

  @override
  Future<void> backup() => _delay(() => _require(Role.admin));

  @override
  Future<List<int>> exportData() => _delay(() {
    _require(Role.owner);
    _needProof();
    return [0x50, 0x4b, 0x05, 0x06];
  });

  // ---- plants and readings -----------------------------------------------------------------------

  @override
  Future<List<Plant>> plants() => _delay(() => List.of(_plants));

  @override
  Future<Plant> createPlant({
    required String name,
    SlotRef sensor = const SlotRef(),
    SlotRef pump = const SlotRef(),
    String notes = '',
  }) => _delay(() {
    _require(Role.member);
    final p = Plant(
      id: 'p${_nextId++}',
      name: name,
      notes: notes,
      sensor: sensor,
      pump: pump,
      moisturePercent: null,
      trend: Trend.steady,
      lastReadingAt: null,
      maxRunS: _pumpLimit(pump),
    );
    _plants.add(p);
    _curves[p.id] = _Curve(Random(p.id.hashCode).nextDouble() * 40 + 30, _clock());
    _emit(LiveEvent(LiveEventKind.plant, entityId: p.id));
    return p;
  });

  int _pumpLimit(SlotRef pump) {
    final cfg = pump.deviceId == null ? null : _configs[pump.deviceId];
    for (final s in cfg?.slots ?? const <SlotConfig>[]) {
      if (s.slot == pump.slot && s.isPump) return s.maxRunS;
    }
    return 0;
  }

  @override
  Future<Plant> updatePlant(String id, {String? name, String? notes, SlotRef? sensor, SlotRef? pump}) =>
      _delay(() {
        _require(Role.member);
        final i = _plants.indexWhere((p) => p.id == id);
        final p = _plants[i];
        _plants[i] = Plant(
          id: p.id,
          name: name ?? p.name,
          notes: notes ?? p.notes,
          sensor: sensor ?? p.sensor,
          pump: pump ?? p.pump,
          moisturePercent: p.moisturePercent,
          trend: p.trend,
          lastReadingAt: p.lastReadingAt,
          maxRunS: pump == null ? p.maxRunS : _pumpLimit(pump),
        );
        _emit(LiveEvent(LiveEventKind.plant, entityId: id));
        return _plants[i];
      });

  @override
  Future<void> deletePlant(String id) => _delay(() {
    _require(Role.member);
    _plants.removeWhere((p) => p.id == id);
    _emit(LiveEvent(LiveEventKind.plant, entityId: id));
  });

  @override
  Future<List<Reading>> readings(String plantId, ChartRange range) => _delay(() {
    final curve = _curves[plantId]!;
    final now = _clock();
    final count = range.span.inMinutes ~/ range.bucket.inMinutes;
    return [
      for (var i = count; i >= 0; i--)
        Reading(now.subtract(range.bucket * i), curve.at(now.subtract(range.bucket * i))),
    ];
  });

  // ---- commands ------------------------------------------------------------------------------------

  @override
  Future<List<Command>> commands(String plantId) => _delay(
    () => _commands.where((c) => c.plantId == plantId).toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt)),
  );

  @override
  Future<Command> waterNow(String plantId, int seconds) => _delay(() {
    _require(Role.member);
    final plant = _plants.firstWhere((p) => p.id == plantId);
    if (!plant.hasPump) throw const ApiProblem(ApiProblem.conflict, status: 409, detail: 'no pump');
    if (seconds < 1 || seconds > plant.maxRunS) {
      throw ApiProblem(ApiProblem.safetyLimit, status: 422, detail: 'max_run_s is ${plant.maxRunS}');
    }
    if (_commands.any((c) => c.plantId == plantId && !c.state.isFinal)) {
      throw const ApiProblem(ApiProblem.busy, status: 409);
    }
    final device = _devices.firstWhere((d) => d.id == plant.pump.deviceId);
    final now = _clock();
    final command = Command(
      id: 'c${_nextId++}',
      plantId: plantId,
      deviceId: device.id,
      seconds: seconds,
      state: CommandState.queued,
      createdAt: now,
      expiresAt: now.add(const Duration(minutes: 15)),
      sent: device.reachable,
    );
    _commands.add(command);
    _emit(LiveEvent(LiveEventKind.command, entityId: plantId));
    if (device.reachable) _simulateDevice(command.id);
    return command;
  });

  @override
  Future<void> cancelCommand(String commandId) => _delay(() {
    _require(Role.member);
    final c = _commands.firstWhere((c) => c.id == commandId);
    if (c.state.isFinal) throw const ApiProblem(ApiProblem.conflict, status: 409);
    _updateCommand(commandId, (c) => c.copyWith(state: CommandState.cancelled, finishedAt: _clock()));
  });

  void _simulateDevice(String commandId) {
    _after(deviceDelay, () {
      final c = _commands.firstWhere((c) => c.id == commandId);
      if (c.state != CommandState.queued) return;
      final until = _clock().add(Duration(seconds: c.seconds));
      _updateCommand(commandId, (c) => c.copyWith(state: CommandState.running, runningUntil: until));
      _after(Duration(seconds: c.seconds), () {
        if (_commands.firstWhere((x) => x.id == commandId).state != CommandState.running) return;
        _updateCommand(commandId, (c) => c.copyWith(state: CommandState.done, finishedAt: _clock()));
        _applyWatering(c.plantId, c.seconds);
      });
    });
  }

  void _applyWatering(String plantId, int seconds) {
    final i = _plants.indexWhere((p) => p.id == plantId);
    final now = _clock();
    final value = min(95.0, (_plants[i].moisturePercent ?? 0) + seconds * 2.5);
    _plants[i] = _plants[i].copyWith(moisturePercent: value, trend: Trend.rising, lastReadingAt: now);
    _curves[plantId] = _curves[plantId]!.wateredTo(value, now);
    _emit(LiveEvent(LiveEventKind.reading, entityId: plantId));
  }

  void _updateCommand(String id, Command Function(Command) update) {
    final i = _commands.indexWhere((c) => c.id == id);
    _commands[i] = update(_commands[i]);
    _emit(LiveEvent(LiveEventKind.command, entityId: _commands[i].plantId));
  }

  // ---- rules -----------------------------------------------------------------------------------------

  @override
  Future<List<Rule>> rules(String plantId) => _delay(() => _rules.where((r) => r.plantId == plantId).toList());

  @override
  Future<Rule> saveRule(Rule rule) => _delay(() {
    _require(Role.member);
    final saved = rule.id.isEmpty
        ? Rule(
            id: 'r${_nextId++}',
            plantId: rule.plantId,
            belowPercent: rule.belowPercent,
            waterSeconds: rule.waterSeconds,
            cooldownS: rule.cooldownS,
            maxPerDay: rule.maxPerDay,
            enabled: rule.enabled,
            quietFrom: rule.quietFrom,
            quietTo: rule.quietTo,
            notifyChannels: rule.notifyChannels,
            notifyOn: rule.notifyOn,
          )
        : rule;
    final index = _rules.indexWhere((r) => r.id == saved.id);
    index < 0 ? _rules.add(saved) : _rules[index] = saved;
    return saved;
  });

  @override
  Future<void> deleteRule(Rule rule) => _delay(() {
    _require(Role.member);
    _rules.removeWhere((r) => r.id == rule.id);
  });

  @override
  Future<List<RuleExecution>> ruleExecutions(String plantId, String ruleId) => _delay(() {
    final now = _clock();
    return [
      RuleExecution(at: now.subtract(const Duration(hours: 5)), decision: 'water', commandId: 'c0'),
      RuleExecution(at: now.subtract(const Duration(hours: 9)), decision: 'skip', skipReason: 'cooldown'),
      RuleExecution(at: now.subtract(const Duration(days: 1)), decision: 'skip', skipReason: 'quiet_hours'),
    ];
  });

  // ---- devices -----------------------------------------------------------------------------------------

  @override
  Future<List<Device>> devices() => _delay(() => List.of(_devices));

  @override
  Future<DeviceConfig> deviceConfig(String deviceId) => _delay(() {
    final d = _devices.firstWhere((d) => d.id == deviceId);
    final desired = _configs[deviceId];
    return DeviceConfig(
      desiredRev: d.desiredRev,
      reportedRev: d.reportedRev,
      sync: d.configSync,
      desired: desired,
      reported: DeviceConfigBody(rev: d.reportedRev ?? 0, slots: d.slots),
      error: d.configError,
      board: d.board,
    );
  });

  @override
  Future<Board?> board(String name) => _delay(
    () => Board(
      name: name,
      ports: [for (var i = 1; i <= 4; i++) BoardPort(id: 'P$i', roles: const ['moisture', 'pump'])],
    ),
  );

  @override
  Future<int> saveDeviceConfig(String deviceId, int baseRev, DeviceConfigBody config) => _delay(() {
    _require(Role.admin);
    final i = _devices.indexWhere((d) => d.id == deviceId);
    final d = _devices[i];
    if (baseRev != d.desiredRev) throw const ApiProblem(ApiProblem.conflict, status: 409);
    final ports = <String>{};
    for (final s in config.slots) {
      if (!ports.add(s.port)) {
        throw ApiProblem(ApiProblem.validation, status: 422, detail: 'slot ${s.slot}: port ${s.port} is used twice');
      }
    }
    final rev = d.desiredRev + 1;
    _configs[deviceId] = DeviceConfigBody(
      rev: rev,
      reportIntervalS: config.reportIntervalS,
      fastReportIntervalS: config.fastReportIntervalS,
      fastReportHoldS: config.fastReportHoldS,
      slots: config.slots,
    );
    _devices[i] = _copy(d, desiredRev: rev, sync: ConfigSync.pending);
    _emit(LiveEvent(LiveEventKind.device, entityId: deviceId));
    _after(deviceDelay, () {
      final j = _devices.indexWhere((x) => x.id == deviceId);
      if (j < 0) return;
      _devices[j] = _copy(_devices[j], reportedRev: rev, sync: ConfigSync.inSync, slots: config.slots);
      _syncPlantLimits();
      _emit(LiveEvent(LiveEventKind.device, entityId: deviceId));
    });
    return rev;
  });

  void _syncPlantLimits() {
    for (var i = 0; i < _plants.length; i++) {
      final p = _plants[i];
      _plants[i] = Plant(
        id: p.id, name: p.name, notes: p.notes, sensor: p.sensor, pump: p.pump,
        moisturePercent: p.moisturePercent, trend: p.trend, lastReadingAt: p.lastReadingAt,
        maxRunS: _pumpLimit(p.pump),
      );
    }
  }

  Device _copy(
    Device d, {
    int? desiredRev,
    int? reportedRev,
    ConfigSync? sync,
    List<SlotConfig>? slots,
    DeviceStatus? status,
    String? name,
    String? configError,
  }) => Device(
    id: d.id,
    name: name ?? d.name,
    status: status ?? d.status,
    configSync: sync ?? d.configSync,
    model: d.model,
    board: d.board,
    firmware: d.firmware,
    safeReason: d.safeReason,
    lastSeen: d.lastSeen,
    linkQuality: d.linkQuality,
    voltageMv: d.voltageMv,
    desiredRev: desiredRev ?? d.desiredRev,
    reportedRev: reportedRev ?? d.reportedRev,
    configError: configError ?? d.configError,
    slots: slots ?? d.slots,
    diagnostics: d.diagnostics,
  );

  @override
  Future<Device> renameDevice(String deviceId, String name) => _delay(() {
    _require(Role.admin);
    final i = _devices.indexWhere((d) => d.id == deviceId);
    _devices[i] = _copy(_devices[i], name: name);
    _emit(LiveEvent(LiveEventKind.device, entityId: deviceId));
    return _devices[i];
  });

  @override
  Future<void> deleteDevice(String deviceId, {bool force = false}) => _delay(() {
    _require(Role.admin);
    _needProof();
    _devices.removeWhere((d) => d.id == deviceId);
    _emit(LiveEvent(LiveEventKind.device, entityId: deviceId));
  });

  @override
  Future<void> deviceAction(String deviceId, DeviceAction action) => _delay(() {
    _require(action == DeviceAction.identify ? Role.member : Role.admin);
    if (action == DeviceAction.clearSafeMode) {
      final i = _devices.indexWhere((d) => d.id == deviceId);
      _devices[i] = _copy(_devices[i], status: DeviceStatus.online);
      _emit(LiveEvent(LiveEventKind.device, entityId: deviceId));
    }
  });

  @override
  Future<List<Map<String, Object?>>> deviceEvents(String deviceId) => _delay(
    () => [
      {'ts': _clock().subtract(const Duration(hours: 3)).toIso8601String(), 'code': 'boot'},
      {'ts': _clock().subtract(const Duration(days: 1)).toIso8601String(), 'code': 'low_battery'},
    ],
  );

  @override
  Future<JoinState> joinState() => _delay(() => _join);

  @override
  Future<JoinState> openJoin({String? installCode, int seconds = 120}) => _delay(() {
    _require(Role.admin);
    final ends = _clock().add(Duration(seconds: seconds));
    _join = JoinState(open: true, endsAt: ends);
    _emit(const LiveEvent(LiveEventKind.join));
    _after(deviceDelay, _joinNewDevice);
    return _join;
  });

  void _joinNewDevice() {
    if (!_join.open) return;
    final id = 'dev-new${_nextId++}';
    _devices.add(
      Device(id: id, name: id, status: DeviceStatus.joining, configSync: ConfigSync.pending, model: 'MC-PLANT'),
    );
    _join = JoinState(open: true, endsAt: _join.endsAt, deviceIds: [..._join.deviceIds, id]);
    _emit(LiveEvent(LiveEventKind.join, entityId: id));
    _after(deviceDelay, () {
      final i = _devices.indexWhere((d) => d.id == id);
      if (i < 0) return;
      _devices[i] = _copy(_devices[i], status: DeviceStatus.ready);
      _emit(LiveEvent(LiveEventKind.device, entityId: id));
      _after(deviceDelay, () {
        final j = _devices.indexWhere((d) => d.id == id);
        if (j < 0) return;
        _devices[j] = Device(
          id: id, name: id, status: DeviceStatus.online, configSync: ConfigSync.inSync,
          model: 'MC-PLANT', board: 'carrier-v1', firmware: '0.1.0', lastSeen: _clock(), linkQuality: 180,
          desiredRev: 1, reportedRev: 1,
        );
        _configs[id] = const DeviceConfigBody(rev: 1);
        _emit(LiveEvent(LiveEventKind.device, entityId: id));
      });
    });
  }

  @override
  Future<void> closeJoin() => _delay(() {
    _require(Role.admin);
    _join = const JoinState();
    _emit(const LiveEvent(LiveEventKind.join));
  });

  // ---- alerts ----------------------------------------------------------------------------------------------

  @override
  Future<List<Alert>> alerts() => _delay(() => List.of(_alerts)..sort((a, b) => b.createdAt.compareTo(a.createdAt)));

  @override
  Future<void> acknowledgeAlert(String alertId) => _delay(() {
    _require(Role.member);
    final i = _alerts.indexWhere((a) => a.id == alertId);
    _alerts[i] = _alerts[i].acknowledge(_clock(), by: _me.id);
    _emit(LiveEvent(LiveEventKind.alert, entityId: alertId));
  });

  @override
  Stream<LiveEvent> events() => _stream.stream;

  // ---- helpers ---------------------------------------------------------------------------------------------

  Future<T> _delay<T>(T Function() body) async {
    if (latency > Duration.zero) await Future<void>.delayed(latency);
    return body();
  }

  void _require(Role min) {
    if (_role.index < min.index) throw const ApiProblem(ApiProblem.forbidden, status: 403);
  }

  void _emit(LiveEvent event) {
    if (!_stream.isClosed) _stream.add(event);
  }

  // ---- seed data ------------------------------------------------------------------------------------------------

  void _seed() {
    final now = _clock();
    DateTime ago(Duration d) => now.subtract(d);

    _users.addAll([
      AppUser(id: 'u-demo', username: 'demo', displayName: 'Demo user', role: _role, createdAt: ago(const Duration(days: 30))),
      AppUser(id: 'u-anna', username: 'anna', displayName: 'Anna', role: Role.member, createdAt: ago(const Duration(days: 12))),
      AppUser(id: 'u-ben', username: 'ben', displayName: 'Ben', role: Role.viewer, createdAt: ago(const Duration(days: 3))),
    ]);
    _passwords.addAll({'demo': 'demo', 'anna': 'anna', 'ben': 'ben'});
    _tokens.addAll([
      TokenInfo(id: 'tok-0', name: 'Demo browser', createdAt: ago(const Duration(days: 2)), lastUsedAt: now, current: true),
      TokenInfo(id: 'tok-x', name: "Philipp's phone", createdAt: ago(const Duration(days: 20)), lastUsedAt: ago(const Duration(days: 4)), current: false),
    ]);
    _token = 'tok-0';

    SlotConfig moisture(int slot, String port) => SlotConfig(slot: slot, module: 'moisture', port: port);
    final slots = [moisture(0, 'P1'), moisture(1, 'P2'), const SlotConfig(slot: 2, module: 'pump', port: 'P3', maxRunS: 30)];

    Device device(
      String id,
      String name,
      DeviceStatus status, {
      int? link = 150,
      int? mv = 3900,
      Duration seen = const Duration(minutes: 2),
      ConfigSync sync = ConfigSync.inSync,
      String? configError,
      String? safeReason,
    }) {
      _configs[id] = DeviceConfigBody(rev: 7, slots: slots);
      return Device(
        id: id, name: name, status: status, configSync: sync, model: 'MC-PLANT', board: 'carrier-v1',
        firmware: '0.1.0', safeReason: safeReason, lastSeen: ago(seen), linkQuality: link, voltageMv: mv,
        desiredRev: sync == ConfigSync.inSync ? 7 : 8, reportedRev: 7, configError: configError, slots: slots,
        diagnostics: const {
          'uptime_s': 86400, 'boot_reason': 'power_on', 'reset_count': 0, 'rejoin_count': 1,
          'last_error': 0, 'free_heap': 143000,
        },
      );
    }

    _devices.addAll([
      device('d1', 'Kitchen window', DeviceStatus.online),
      device('d2', 'Bathroom shelf', DeviceStatus.online, sync: ConfigSync.pending),
      device('d3', 'Balcony', DeviceStatus.late, link: 60, seen: const Duration(minutes: 40)),
      device('d4', 'Office', DeviceStatus.offline, link: null, seen: const Duration(days: 2),
          sync: ConfigSync.rejected, configError: 'rejected (port P3 cannot drive this module)'),
      device('d5', 'Greenhouse', DeviceStatus.safeMode, safeReason: 'crash_loop'),
    ]);

    Plant plant(String id, String name, String device, int sensorSlot, double? value, Trend trend, Duration seen, {bool pump = true}) {
      _curves[id] = _Curve(value ?? 50, now);
      return Plant(
        id: id, name: name, sensor: SlotRef(deviceId: device, slot: sensorSlot),
        pump: pump ? SlotRef(deviceId: device, slot: 2) : const SlotRef(),
        moisturePercent: value, trend: trend, lastReadingAt: value == null ? null : ago(seen), maxRunS: pump ? 30 : 0,
      );
    }

    _plants.addAll([
      plant('p1', 'Monstera', 'd1', 0, 18, Trend.falling, const Duration(minutes: 3)),
      plant('p2', 'Basil', 'd1', 1, 47, Trend.steady, const Duration(minutes: 3)),
      plant('p3', 'Ficus', 'd2', 0, 72, Trend.rising, const Duration(minutes: 1)),
      plant('p4', 'Geranium', 'd3', 0, 35, Trend.falling, const Duration(minutes: 40)),
      plant('p5', 'Aloe', 'd4', 0, 22, Trend.steady, const Duration(days: 2), pump: false),
      plant('p6', 'Tomatoes', 'd5', 0, null, Trend.steady, Duration.zero),
    ]);

    _rules.add(
      const Rule(id: 'r1', plantId: 'p1', belowPercent: 25, waterSeconds: 10, cooldownS: 21600, maxPerDay: 2, enabled: true),
    );
    _commands.add(
      Command(id: 'c0', plantId: 'p1', deviceId: 'd1', seconds: 8, state: CommandState.done,
          createdAt: ago(const Duration(hours: 5)), finishedAt: ago(const Duration(hours: 5)), origin: CommandOrigin.rule),
    );
    _alerts.addAll([
      Alert(id: 'a1', kind: AlertKind.deviceOffline, kindName: 'device_offline', subject: 'Office',
          createdAt: ago(const Duration(days: 2)), open: true),
      Alert(id: 'a2', kind: AlertKind.safeMode, kindName: 'device_safe_mode', subject: 'Greenhouse',
          createdAt: ago(const Duration(hours: 1)), open: true, critical: true),
      Alert(id: 'a3', kind: AlertKind.batteryLow, kindName: 'battery_low', subject: 'Balcony',
          createdAt: ago(const Duration(days: 4)), open: false, acknowledgedAt: ago(const Duration(days: 3)), acknowledgedBy: 'u-anna'),
    ]);
    _invites.add(Invite(id: 'i0', role: Role.member, status: 'open', expiresAt: now.add(const Duration(hours: 30))));
    _inviteCodes['DEMOINVITE'] = 'i0';
  }
}

/// A synthetic moisture curve for the charts: slow decay with a daily wobble.
class _Curve {
  _Curve(this.current, this.at0, {double? wateredAt, DateTime? wateredTime})
    : _wateredAt = wateredAt,
      _wateredTime = wateredTime;

  final double current;
  final DateTime at0;
  final double? _wateredAt;
  final DateTime? _wateredTime;

  double at(DateTime t) {
    final hours = at0.difference(t).inMinutes / 60;
    var v = current + hours * 0.35 + sin(t.millisecondsSinceEpoch / 4.3e6) * 3;
    if (_wateredTime != null && t.isAfter(_wateredTime)) v = _wateredAt!;
    return v.clamp(5, 95).toDouble();
  }

  _Curve wateredTo(double value, DateTime when) =>
      _Curve(current, at0, wateredAt: value, wateredTime: when);
}
