import 'dart:async';
import 'dart:math';

import '../api_problem.dart';
import '../models.dart';
import 'moisture_repository.dart';

/// In-memory backend for development without a server.
///
/// Mirrors the backend's behaviour closely enough to exercise the UI: role
/// checks, pump limits, and commands that go queued → delivered → running →
/// done over a few seconds with live events, like a real sleeping device.
class FakeMoistureRepository implements MoistureRepository {
  FakeMoistureRepository({
    DateTime Function()? clock,
    this.latency = const Duration(milliseconds: 250),
    this.deviceDelay = const Duration(seconds: 5),
  }) : _clock = clock ?? DateTime.now {
    _seed();
  }

  final DateTime Function() _clock;

  /// Simulated network round trip.
  final Duration latency;

  /// Time until a "sleeping" device wakes up and picks up a command.
  final Duration deviceDelay;

  final _households = <String, Household>{};
  final _plants = <String, List<Plant>>{};
  final _devices = <String, List<Device>>{};
  final _commands = <String, List<Command>>{};
  final _rules = <String, List<Rule>>{};
  final _alerts = <String, List<Alert>>{};
  final _gateways = <String, GatewayInfo?>{};
  final _curves = <String, _Curve>{};
  final _streams = <String, StreamController<LiveEvent>>{};
  final _timers = <Timer>[];
  var _nextId = 1;

  /// Dev-only: lets the settings screen switch the demo role per household.
  void setRole(String householdId, Role role) {
    _households[householdId] = _households[householdId]!.copyWith(role: role);
    _emit(householdId, const LiveEvent(LiveEventKind.household));
  }

  void dispose() {
    for (final t in _timers) {
      t.cancel();
    }
    for (final s in _streams.values) {
      s.close();
    }
  }

  // --- MoistureRepository ---------------------------------------------------

  @override
  Future<List<Household>> households() =>
      _delay(() => _households.values.toList());

  @override
  Future<List<Plant>> plants(String householdId) =>
      _delay(() => List.of(_plants[householdId]!));

  @override
  Future<List<Reading>> readings(
    String householdId,
    String plantId,
    ChartRange range,
  ) => _delay(() {
    final curve = _curves[plantId]!;
    final now = _clock();
    final count = range.span.inMinutes ~/ range.bucket.inMinutes;
    return [
      for (var i = count; i >= 0; i--)
        Reading(
          now.subtract(range.bucket * i),
          curve.at(now.subtract(range.bucket * i)),
        ),
    ];
  });

  @override
  Future<List<Command>> commands(String householdId, String plantId) =>
      _delay(() {
        final list =
            (_commands[householdId] ?? [])
                .where((c) => c.plantId == plantId)
                .toList()
              ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
        return list;
      });

  @override
  Future<Command> waterNow(String householdId, String plantId, int seconds) =>
      _delay(() {
        _requireRole(householdId, Role.member);
        final plant = _plant(householdId, plantId);
        if (seconds < 1 || seconds > plant.maxRunS) {
          throw ApiProblem(
            ApiProblem.safetyLimit,
            status: 422,
            detail: 'max_run_s is ${plant.maxRunS}',
          );
        }
        final now = _clock();
        final command = Command(
          id: 'c${_nextId++}',
          plantId: plantId,
          seconds: seconds,
          state: CommandState.queued,
          createdAt: now,
          expectedAt: now.add(deviceDelay),
        );
        _commands.putIfAbsent(householdId, () => []).add(command);
        _emit(householdId, LiveEvent(LiveEventKind.command, entityId: plantId));
        _simulateDevice(householdId, command.id);
        return command;
      });

  @override
  Future<void> cancelCommand(String householdId, String commandId) =>
      _delay(() {
        _requireRole(householdId, Role.member);
        final command = _command(householdId, commandId);
        if (command.state != CommandState.queued) {
          throw const ApiProblem(ApiProblem.tooLate, status: 409);
        }
        _updateCommand(
          householdId,
          commandId,
          (c) =>
              c.copyWith(state: CommandState.cancelled, finishedAt: _clock()),
        );
      });

  @override
  Future<List<Rule>> rules(String householdId, String plantId) => _delay(
    () =>
        (_rules[householdId] ?? []).where((r) => r.plantId == plantId).toList(),
  );

  @override
  Future<Rule> saveRule(String householdId, Rule rule) => _delay(() {
    _requireRole(householdId, Role.member);
    final list = _rules.putIfAbsent(householdId, () => []);
    final saved = rule.id.isEmpty
        ? Rule(
            id: 'r${_nextId++}',
            plantId: rule.plantId,
            belowPercent: rule.belowPercent,
            waterSeconds: rule.waterSeconds,
            minIntervalHours: rule.minIntervalHours,
            enabled: rule.enabled,
          )
        : rule;
    final index = list.indexWhere((r) => r.id == saved.id);
    index < 0 ? list.add(saved) : list[index] = saved;
    return saved;
  });

  @override
  Future<void> deleteRule(String householdId, Rule rule) => _delay(() {
    _requireRole(householdId, Role.member);
    _rules[householdId]?.removeWhere((r) => r.id == rule.id);
  });

  @override
  Future<List<Device>> devices(String householdId) =>
      _delay(() => List.of(_devices[householdId]!));

  var _newDevices = 0;

  @override
  Future<NewDevice> createDevice(String householdId, String name) => _delay(() {
    _requireRole(householdId, Role.admin);
    final gateway = _gateways[householdId];
    if (gateway == null) {
      throw const ApiProblem(ApiProblem.noGateway, status: 409);
    }
    if (!gateway.online) {
      throw const ApiProblem(ApiProblem.gatewayOffline, status: 409);
    }
    final n = ++_newDevices;
    final now = _clock();
    final device = Device(
      id: 'mc-new${n.toString().padLeft(12, '0')}',
      name: name,
      board: 'doit_esp32_devkit_v1',
      firmware: '—',
      batteryPercent: 0,
      rssi: 0,
      state: DeviceState.offline,
      lastSeen: now,
      nextExpectedAt: now,
      wakeIntervalS: 600,
      configSync: ConfigSync.pending,
      configRev: 0,
      slots: const [],
    );
    _devices[householdId] = [...?_devices[householdId], device];
    _emit(householdId, const LiveEvent(LiveEventKind.device));
    return NewDevice(device, _bundleFor(device.id, gateway));
  });

  PairingBundle _bundleFor(String deviceId, GatewayInfo gateway) => PairingBundle(
    deviceId: deviceId,
    host: gateway.lanHostOverride ?? gateway.lanHost ?? '192.168.1.20',
    port: gateway.lanPort,
    psk: 'ab' * 32,
  );

  @override
  Future<PairingBundle> rekeyDevice(String householdId, String deviceId) =>
      _delay(() {
        _requireRole(householdId, Role.admin);
        final gateway = _gateways[householdId];
        if (gateway == null) {
          throw const ApiProblem(ApiProblem.noGateway, status: 409);
        }
        return _bundleFor(deviceId, gateway);
      });

  @override
  Future<void> deleteDevice(String householdId, String deviceId) => _delay(() {
    _requireRole(householdId, Role.admin);
    _devices[householdId] = [
      for (final d in _devices[householdId]!)
        if (d.id != deviceId) d,
    ];
    _emit(householdId, const LiveEvent(LiveEventKind.device));
  });

  /// Test helper: a paired device connects for the first time.
  void simulateDeviceOnline(String householdId, String deviceId) {
    _devices[householdId] = [
      for (final d in _devices[householdId]!)
        if (d.id == deviceId)
          d.copyWith(state: DeviceState.online, lastSeen: _clock())
        else
          d,
    ];
    _emit(householdId, const LiveEvent(LiveEventKind.device));
  }

  @override
  Future<void> deviceAction(
    String householdId,
    String deviceId,
    DeviceAction action,
  ) => _delay(
    () => _requireRole(
      householdId,
      action == DeviceAction.identify ? Role.member : Role.admin,
    ),
  );

  @override
  Future<List<Alert>> alerts(String householdId) => _delay(
    () =>
        List.of(_alerts[householdId] ?? [])
          ..sort((a, b) => b.createdAt.compareTo(a.createdAt)),
  );

  @override
  Future<void> acknowledgeAlert(String householdId, String alertId) =>
      _delay(() {
        _requireRole(householdId, Role.member);
        final list = _alerts[householdId]!;
        final i = list.indexWhere((a) => a.id == alertId);
        list[i] = list[i].acknowledge(_clock());
        _emit(householdId, LiveEvent(LiveEventKind.alert, entityId: alertId));
      });

  // --- gateway ------------------------------------------------------------------------

  @override
  Future<GatewayInfo?> gateway(String householdId) =>
      _delay(() => _gateways[householdId]);

  @override
  Future<GatewayInfo> claimGateway(String householdId, String userCode) =>
      _delay(() {
        _requireRole(householdId, Role.admin);
        final code = userCode.replaceAll(RegExp(r'[\s-]'), '');
        if (!RegExp(r'^[0-9A-Za-z]{8}$').hasMatch(code)) {
          throw const ApiProblem(ApiProblem.invalidCode, status: 422);
        }
        if (_gateways[householdId] != null) {
          throw const ApiProblem(ApiProblem.gatewayExists, status: 409);
        }
        // A new gateway: every device must be re-paired to it.
        _devices[householdId] = [
          for (final d in _devices[householdId]!)
            _withGateway(d, GatewayLink.none),
        ];
        _setGateway(
          householdId,
          _gatewayInfo('enrolling', online: false, inSync: false),
        );
        // Simulate the gateway fetching its credential, connecting and syncing.
        _timers.add(
          Timer(const Duration(seconds: 3), () {
            _setGateway(
              householdId,
              _gatewayInfo('online', online: true, inSync: false),
            );
          }),
        );
        _timers.add(
          Timer(const Duration(seconds: 5), () {
            _setGateway(
              householdId,
              _gatewayInfo('online', online: true, inSync: true),
            );
          }),
        );
        _emit(householdId, const LiveEvent(LiveEventKind.device));
        return _gateways[householdId]!;
      });

  @override
  Future<GatewayInfo> setGatewayLanHost(
    String householdId,
    String? lanHostOverride,
  ) => _delay(() {
    _requireRole(householdId, Role.admin);
    final h = _gateways[householdId]!;
    _setGateway(
      householdId,
      GatewayInfo(
        id: h.id,
        status: h.status,
        online: h.online,
        inSync: h.inSync,
        offlineSince: h.offlineSince,
        version: h.version,
        latestVersion: h.latestVersion,
        arch: h.arch,
        adapters: h.adapters,
        outboxDepth: h.outboxDepth,
        timeSynced: h.timeSynced,
        lanHost: lanHostOverride ?? '192.168.1.20',
        lanHostOverride: lanHostOverride,
        lastStateAt: h.lastStateAt,
      ),
    );
    return _gateways[householdId]!;
  });

  @override
  Future<void> removeGateway(String householdId) => _delay(() {
    _requireRole(householdId, Role.admin);
    _devices[householdId] = [
      for (final d in _devices[householdId]!) _withGateway(d, GatewayLink.none),
    ];
    _setGateway(householdId, null);
    _emit(householdId, const LiveEvent(LiveEventKind.device));
  });

  GatewayInfo _gatewayInfo(
    String status, {
    required bool online,
    required bool inSync,
  }) => GatewayInfo(
    id: 'gw-4k9m2x7q1v8w3h5t',
    status: status,
    online: online,
    inSync: inSync,
    offlineSince: online ? null : _clock(),
    version: online ? '0.1.0' : null,
    latestVersion: '0.1.0',
    arch: 'arm64',
    adapters: const ['esp32-mqtt'],
    outboxDepth: 0,
    timeSynced: online ? true : null,
    lanHost: online ? '192.168.1.20' : null,
    lastStateAt: online ? _clock() : null,
  );

  void _setGateway(String householdId, GatewayInfo? gateway) {
    _gateways[householdId] = gateway;
    final h = _households[householdId]!;
    _households[householdId] = Household(
      id: h.id,
      name: h.name,
      timezone: h.timezone,
      role: h.role,
      gateway: gateway == null
          ? null
          : GatewayStatus(
              online: gateway.online,
              offlineSince: gateway.offlineSince,
            ),
    );
    _emit(householdId, const LiveEvent(LiveEventKind.gateway));
  }

  Device _withGateway(Device d, GatewayLink g) => Device(
    id: d.id,
    name: d.name,
    board: d.board,
    firmware: d.firmware,
    batteryPercent: d.batteryPercent,
    rssi: d.rssi,
    state: d.state,
    lastSeen: d.lastSeen,
    nextExpectedAt: d.nextExpectedAt,
    wakeIntervalS: d.wakeIntervalS,
    configSync: d.configSync,
    configRev: d.configRev,
    configError: d.configError,
    slots: d.slots,
    gateway: g,
  );

  @override
  Stream<LiveEvent> events(String householdId) => _stream(householdId).stream;

  // --- Simulation -------------------------------------------------------------

  void _simulateDevice(String householdId, String commandId) {
    void after(Duration d, void Function() f) => _timers.add(Timer(d, f));

    after(deviceDelay, () {
      final c = _command(householdId, commandId);
      if (c.state != CommandState.queued) return;
      _updateCommand(
        householdId,
        commandId,
        (c) => c.copyWith(state: CommandState.delivered),
      );

      after(const Duration(seconds: 1), () {
        final c = _command(householdId, commandId);
        final until = _clock().add(Duration(seconds: c.seconds));
        _updateCommand(
          householdId,
          commandId,
          (c) => c.copyWith(state: CommandState.running, runningUntil: until),
        );

        after(Duration(seconds: c.seconds), () {
          _updateCommand(
            householdId,
            commandId,
            (c) => c.copyWith(state: CommandState.done, finishedAt: _clock()),
          );
          _applyWatering(householdId, c.plantId, c.seconds);
        });
      });
    });
  }

  void _applyWatering(String householdId, String plantId, int seconds) {
    final plants = _plants[householdId]!;
    final i = plants.indexWhere((p) => p.id == plantId);
    final now = _clock();
    final value = min(95.0, (plants[i].moisturePercent ?? 0) + seconds * 2.5);
    plants[i] = plants[i].copyWith(
      moisturePercent: value,
      trend: Trend.rising,
      lastReadingAt: now,
    );
    _curves[plantId] = _curves[plantId]!.wateredTo(value, now);
    _emit(householdId, LiveEvent(LiveEventKind.reading, entityId: plantId));
  }

  // --- Helpers ----------------------------------------------------------------

  Future<T> _delay<T>(T Function() body) async {
    if (latency > Duration.zero) await Future<void>.delayed(latency);
    return body();
  }

  void _requireRole(String householdId, Role min) {
    if (_households[householdId]!.role.index < min.index) {
      throw const ApiProblem(ApiProblem.forbidden, status: 403);
    }
  }

  Plant _plant(String householdId, String plantId) =>
      _plants[householdId]!.firstWhere((p) => p.id == plantId);

  Command _command(String householdId, String commandId) =>
      _commands[householdId]!.firstWhere((c) => c.id == commandId);

  void _updateCommand(
    String householdId,
    String commandId,
    Command Function(Command) update,
  ) {
    final list = _commands[householdId]!;
    final i = list.indexWhere((c) => c.id == commandId);
    list[i] = update(list[i]);
    _emit(
      householdId,
      LiveEvent(LiveEventKind.command, entityId: list[i].plantId),
    );
  }

  StreamController<LiveEvent> _stream(String householdId) =>
      _streams.putIfAbsent(householdId, StreamController<LiveEvent>.broadcast);

  void _emit(String householdId, LiveEvent event) {
    final s = _streams[householdId];
    if (s != null && !s.isClosed) s.add(event);
  }

  // --- Seed data --------------------------------------------------------------

  void _seed() {
    final now = _clock();
    DateTime ago(Duration d) => now.subtract(d);

    _households['h1'] = const Household(
      id: 'h1',
      name: 'Home',
      timezone: 'Europe/Berlin',
      role: Role.owner,
      gateway: GatewayStatus(online: true, version: '1.2.0'),
    );
    _households['h2'] = Household(
      id: 'h2',
      name: "Parents' garden",
      timezone: 'Europe/Berlin',
      role: Role.viewer,
      gateway: GatewayStatus(
        online: false,
        offlineSince: ago(const Duration(hours: 3)),
        version: '1.1.4',
      ),
    );

    Device device(
      String id,
      String name,
      DeviceState state, {
      int battery = 80,
      int rssi = -62,
      Duration lastSeen = const Duration(minutes: 12),
      ConfigSync sync = ConfigSync.inSync,
      String? configError,
    }) => Device(
      id: id,
      name: name,
      board: 'doit_esp32_devkit_v1',
      firmware: '0.4.2',
      batteryPercent: battery,
      rssi: rssi,
      state: state,
      lastSeen: ago(lastSeen),
      nextExpectedAt: ago(lastSeen).add(const Duration(minutes: 30)),
      wakeIntervalS: 1800,
      configSync: sync,
      configRev: 7,
      configError: configError,
      gateway: GatewayLink.gateway,
      slots: const [
        Slot(index: 0, module: 'capacitive_moisture', pin: 34),
        Slot(index: 1, module: 'capacitive_moisture', pin: 35),
        Slot(index: 2, module: 'pump', pin: 26, maxRunS: 30),
      ],
    );

    _gateways['h1'] = GatewayInfo(
      id: 'gw-4k9m2x7q1v8w3h5t',
      status: 'online',
      online: true,
      inSync: true,
      version: '0.1.0',
      latestVersion: '0.2.0',
      arch: 'arm64',
      adapters: const ['esp32-mqtt'],
      outboxDepth: 0,
      timeSynced: true,
      lanHost: '192.168.1.20',
      lastStateAt: ago(const Duration(minutes: 4)),
    );
    _gateways['h2'] = GatewayInfo(
      id: 'gw-7c2m9x1q4v8w3h5z',
      status: 'offline',
      online: false,
      inSync: true,
      offlineSince: ago(const Duration(hours: 3)),
      version: '0.1.0',
      latestVersion: '0.2.0',
      arch: 'amd64',
      adapters: const ['esp32-mqtt'],
      outboxDepth: 212,
      timeSynced: true,
      lanHost: '192.168.178.40',
      lastStateAt: ago(const Duration(hours: 3)),
    );

    _devices['h1'] = [
      device('d1', 'Kitchen window', DeviceState.sleeping, battery: 18),
      device(
        'd2',
        'Bathroom shelf',
        DeviceState.online,
        lastSeen: const Duration(minutes: 1),
        sync: ConfigSync.pending,
      ),
      device(
        'd3',
        'Balcony',
        DeviceState.late,
        rssi: -81,
        lastSeen: const Duration(hours: 2),
      ),
      device(
        'd4',
        'Office',
        DeviceState.offline,
        battery: 0,
        lastSeen: const Duration(days: 2),
        sync: ConfigSync.rejected,
        configError: 'GPIO 34 is input-only',
      ),
    ];
    _devices['h2'] = [
      device(
        'd5',
        'Rose bed',
        DeviceState.sleeping,
        lastSeen: const Duration(hours: 3, minutes: 5),
      ),
      device(
        'd6',
        'Orchard',
        DeviceState.sleeping,
        battery: 64,
        lastSeen: const Duration(hours: 3, minutes: 20),
      ),
    ];

    Plant plant(
      String id,
      String name,
      String deviceId,
      double moisture,
      Trend trend,
      Duration age, {
      int maxRunS = 30,
    }) {
      _curves[id] = _Curve.through(moisture, now, seed: id.hashCode);
      return Plant(
        id: id,
        name: name,
        deviceId: deviceId,
        moisturePercent: moisture,
        trend: trend,
        lastReadingAt: ago(age),
        maxRunS: maxRunS,
      );
    }

    _plants['h1'] = [
      plant(
        'p1',
        'Basil',
        'd1',
        22,
        Trend.falling,
        const Duration(minutes: 12),
      ),
      plant(
        'p2',
        'Monstera',
        'd1',
        48,
        Trend.steady,
        const Duration(minutes: 12),
      ),
      plant('p3', 'Fern', 'd2', 81, Trend.rising, const Duration(minutes: 1)),
      plant(
        'p4',
        'Tomatoes',
        'd3',
        35,
        Trend.falling,
        const Duration(hours: 2),
      ),
      plant(
        'p5',
        'Lemon tree',
        'd4',
        12,
        Trend.falling,
        const Duration(days: 2),
      ),
    ];
    _plants['h2'] = [
      plant(
        'p6',
        'Roses',
        'd5',
        57,
        Trend.steady,
        const Duration(hours: 3, minutes: 5),
      ),
      plant(
        'p7',
        'Apple tree',
        'd6',
        29,
        Trend.falling,
        const Duration(hours: 3, minutes: 20),
        maxRunS: 120,
      ),
    ];

    _rules['h1'] = [
      const Rule(
        id: 'r1',
        plantId: 'p1',
        belowPercent: 30,
        waterSeconds: 10,
        minIntervalHours: 6,
        enabled: true,
      ),
    ];

    _commands['h1'] = [
      Command(
        id: 'c0',
        plantId: 'p1',
        seconds: 10,
        state: CommandState.done,
        createdAt: ago(const Duration(hours: 26)),
        expectedAt: ago(const Duration(hours: 26)),
        finishedAt: ago(const Duration(hours: 25, minutes: 40)),
        origin: CommandOrigin.rule,
      ),
    ];

    _alerts['h1'] = [
      Alert(
        id: 'a1',
        kind: AlertKind.batteryLow,
        subject: 'Kitchen window',
        createdAt: ago(const Duration(hours: 5)),
        open: true,
      ),
      Alert(
        id: 'a2',
        kind: AlertKind.deviceOffline,
        subject: 'Office',
        createdAt: ago(const Duration(days: 2)),
        open: true,
      ),
      Alert(
        id: 'a3',
        kind: AlertKind.sensorSuspect,
        subject: 'Fern',
        createdAt: ago(const Duration(days: 6)),
        open: false,
        acknowledgedAt: ago(const Duration(days: 5)),
      ),
    ];
    _alerts['h2'] = [];
  }
}

/// Sawtooth drying curve with small noise: dries from [_high] to [_low] over
/// [_period], then gets watered back up.
class _Curve {
  _Curve(this._low, this._high, this._period, this._anchor, this._seed);

  factory _Curve.through(double current, DateTime now, {required int seed}) {
    final rnd = Random(seed);
    final low = 15 + rnd.nextDouble() * 10;
    final high = max(current + 5, 70 + rnd.nextDouble() * 15);
    final period = Duration(hours: 72 + rnd.nextInt(72));
    // Place the last watering so that at(now) == current.
    final frac = ((high - current) / (high - low)).clamp(0.0, 0.999);
    final anchor = now.subtract(period * frac);
    return _Curve(low, high, period, anchor, seed);
  }

  final double _low;
  final double _high;
  final Duration _period;

  /// Time of a watering (curve at [_high]).
  final DateTime _anchor;
  final int _seed;

  double at(DateTime t) {
    final hours = t.difference(_anchor).inMinutes / 60;
    final periodH = _period.inMinutes / 60;
    var frac = (hours / periodH) % 1;
    if (frac < 0) frac += 1;
    final base = _high - (_high - _low) * frac;
    final noise = sin(hours * 1.7 + _seed) * 0.8;
    return (base + noise).clamp(0, 100).toDouble();
  }

  _Curve wateredTo(double value, DateTime now) =>
      _Curve(_low, max(value, _low + 1), _period, now, _seed);
}
