import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import '../api/sse.dart';
import '../api_problem.dart';
import '../models.dart';
import 'moisture_repository.dart';

/// Talks to the gateway's api (`/api/v1`, Gateway/specs.md Part A §6).
///
/// Hand-written until a Dart client is generated from the api's OpenAPI document; it maps the api's
/// JSON onto the app's models.
class ApiMoistureRepository implements MoistureRepository {
  ApiMoistureRepository({
    required String baseUrl,
    String appHeader = 'web/0.1.0',
    HttpClientAdapter? httpAdapter, // tests
    DateTime Function()? now,
  }) : _base = Uri.parse(baseUrl),
       _now = now ?? DateTime.now,
       _dio = Dio(
         BaseOptions(
           baseUrl: '$baseUrl/api/v1',
           connectTimeout: const Duration(seconds: 10),
           receiveTimeout: const Duration(seconds: 20),
           headers: {'X-MC-App': appHeader},
         ),
       ) {
    if (httpAdapter != null) _dio.httpClientAdapter = httpAdapter;
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          final token = _token;
          if (token != null) options.headers['Authorization'] = 'Bearer $token';
          final proof = _proof;
          if (proof != null && _now().isBefore(_proofUntil)) {
            options.headers['X-MC-Reauth'] = proof;
          }
          handler.next(options);
        },
      ),
    );
  }

  Uri _base;
  final Dio _dio;
  final DateTime Function() _now;
  String? _token;
  String? _proof;
  DateTime _proofUntil = DateTime.fromMillisecondsSinceEpoch(0);

  /// The address pages and invite links are served from (`http://moisture.local`).
  String get origin => _base.origin;

  /// Called when a request failed because the server could not be reached
  /// (not for HTTP error answers); the app then looks for the server again.
  void Function()? onUnreachable;

  /// Called when the api no longer accepts the stored token (revoked, user removed).
  void Function()? onUnauthorized;

  /// Points the repository at another server (LAN discovery, App/specs.md Part A §6.4).
  void setBaseUrl(Uri baseUrl) {
    _base = baseUrl;
    _dio.options.baseUrl = '$baseUrl/api/v1';
  }

  @override
  void useToken(String? token) {
    _token = token;
    if (token == null) _proof = null;
  }

  // ---- plumbing ------------------------------------------------------------------------------

  /// GETs are retried with backoff (max 3); writes never (App/specs.md Part A §6.1).
  Future<dynamic> _get(String path, [Map<String, dynamic>? query]) async {
    for (var attempt = 0; ; attempt++) {
      try {
        return await _call(() => _dio.get(path, queryParameters: query));
      } on ApiProblem catch (e) {
        if (e.type != ApiProblem.network || attempt >= 2) rethrow;
        await Future<void>.delayed(Duration(milliseconds: 300 << attempt));
      }
    }
  }

  Future<dynamic> _send(String method, String path, [Object? body, Map<String, dynamic>? query]) => _call(
    () => _dio.request(path, data: body, queryParameters: query, options: Options(method: method)),
  );

  Future<dynamic> _call(Future<Response<dynamic>> Function() request) async {
    try {
      return (await request()).data;
    } on DioException catch (e) {
      final data = e.response?.data;
      final status = e.response?.statusCode ?? 0;
      if (data is Map && data['code'] is String) {
        final code = data['code'] as String;
        if (status == 401 && code == ApiProblem.unauthorized) onUnauthorized?.call();
        throw ApiProblem(code, status: status, detail: data['detail'] as String?);
      }
      if (e.response == null) onUnreachable?.call();
      throw ApiProblem(ApiProblem.network, status: status, detail: e.message);
    }
  }

  static DateTime? _dt(Object? v) =>
      v == null ? null : DateTime.parse(v as String).toLocal();

  static Map _map(Object? v) => (v as Map?) ?? const {};
  static List _list(Object? v) => (v as List?) ?? const [];

  // ---- sign-in -------------------------------------------------------------------------------

  AppUser _user(Map u) => AppUser(
    id: u['id'] as String,
    username: u['username'] as String,
    displayName: (u['display_name'] ?? u['username']) as String,
    role: Role.values.byName(u['role'] as String),
    disabled: (u['disabled'] as bool?) ?? false,
    createdAt: _dt(u['created_at']),
  );

  Session _session(Object? r) =>
      Session(token: _map(r)['token'] as String, user: _user(_map(_map(r)['user'])));

  @override
  Future<GatewayMeta> meta() async {
    final m = _map(await _get('/meta'));
    final hub = _map(m['hub']);
    return GatewayMeta(
      name: (m['name'] ?? '') as String,
      setupRequired: m['setup_required'] as bool,
      hubOnline: (hub['online'] as bool?) ?? false,
      hubCompatible: (hub['compatible'] as bool?) ?? true,
      version: m['version'] as String?,
    );
  }

  @override
  Future<Session> setup({
    required String setupCode,
    required String name,
    required String timezone,
    required String username,
    required String password,
    String displayName = '',
  }) async => _session(
    await _send('POST', '/setup', {
      'setup_code': setupCode.trim(),
      'name': name,
      'timezone': timezone,
      'username': username,
      'password': password,
      'display_name': displayName,
    }),
  );

  @override
  Future<Session> login({
    required String username,
    required String password,
    String deviceName = '',
  }) async => _session(
    await _send('POST', '/auth/login', {
      'username': username,
      'password': password,
      'device_name': deviceName,
    }),
  );

  @override
  Future<InvitePreview> previewInvite(String code) async {
    final r = _map(await _get('/invites/${Uri.encodeComponent(code)}'));
    return InvitePreview(
      role: Role.values.byName(r['role'] as String),
      installation: (r['installation'] ?? '') as String,
    );
  }

  @override
  Future<Session> acceptInvite({
    required String code,
    required String username,
    required String password,
    String displayName = '',
    String deviceName = '',
  }) async => _session(
    await _send('POST', '/invites/${Uri.encodeComponent(code)}/accept', {
      'username': username,
      'password': password,
      'display_name': displayName,
      'device_name': deviceName,
    }),
  );

  @override
  Future<AppUser> me() async => _user(_map(await _get('/me')));

  @override
  Future<void> logout() async {
    try {
      await _send('POST', '/auth/logout');
    } on ApiProblem {
      // already signed out on the server: nothing left to do
    }
  }

  @override
  Future<AppUser> updateMe({String? displayName}) async =>
      _user(_map(await _send('PATCH', '/me', {'display_name': displayName})));

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) => _send('PATCH', '/me', {
    'password': newPassword,
    'current_password': currentPassword,
  });

  @override
  Future<void> reauth(String password) async {
    final r = _map(await _send('POST', '/auth/reauth', {'password': password}));
    _proof = r['proof'] as String;
    _proofUntil = _now().add(Duration(seconds: ((r['expires_in'] as int?) ?? 300) - 5));
  }

  // ---- tokens, users, invites, audit -----------------------------------------------------------

  @override
  Future<List<TokenInfo>> tokens() async => [
    for (final t in _list(await _get('/auth/tokens')).cast<Map>())
      TokenInfo(
        id: t['id'] as String,
        name: (t['name'] ?? '') as String,
        createdAt: _dt(t['created_at'])!,
        lastUsedAt: _dt(t['last_used_at']),
        current: (t['current'] as bool?) ?? false,
      ),
  ];

  @override
  Future<void> revokeToken(String id) => _send('DELETE', '/auth/tokens/$id');

  @override
  Future<List<AppUser>> users() async => [
    for (final u in _list(await _get('/users')).cast<Map>()) _user(u),
  ];

  @override
  Future<AppUser> updateUser(
    String id, {
    Role? role,
    String? displayName,
    bool? disabled,
  }) async => _user(
    _map(
      await _send('PATCH', '/users/$id', {
        'role': ?role?.name,
        'display_name': ?displayName,
        'disabled': ?disabled,
      }),
    ),
  );

  @override
  Future<void> deleteUser(String id) => _send('DELETE', '/users/$id');

  @override
  Future<void> transferOwnership(String userId) =>
      _send('POST', '/transfer-ownership', {'user_id': userId});

  Invite _invite(Map i) => Invite(
    id: i['id'] as String,
    role: Role.values.byName(i['role'] as String),
    status: i['status'] as String,
    expiresAt: _dt(i['expires_at'])!,
  );

  @override
  Future<List<Invite>> invites() async => [
    for (final i in _list(await _get('/invites')).cast<Map>()) _invite(i),
  ];

  @override
  Future<CreatedInvite> createInvite(Role role, {Duration? expiresIn}) async {
    final r = _map(
      await _send('POST', '/invites', {
        'role': role.name,
        'expires_in': ?expiresIn?.inSeconds,
      }),
    );
    return CreatedInvite(invite: _invite(r), code: r['code'] as String);
  }

  @override
  Future<void> revokeInvite(String id) => _send('DELETE', '/invites/$id');

  @override
  Future<List<AuditEntry>> audit({int? before, int limit = 100}) async {
    final r = _map(await _get('/audit', {'limit': limit, 'before': ?before}));
    return [
      for (final a in _list(r['items']).cast<Map>())
        AuditEntry(
          id: a['id'] as int,
          actor: (a['actor'] ?? '') as String,
          action: a['action'] as String,
          at: _dt(a['ts'])!,
          detail: (a['detail'] as Map?)?.cast<String, Object?>(),
        ),
    ];
  }

  // ---- installation and gateway ------------------------------------------------------------------

  Installation _installation(Map i) => Installation(
    name: (i['name'] ?? '') as String,
    timezone: (i['timezone'] ?? 'UTC') as String,
    batteryLowMv: (i['battery_low_mv'] as int?) ?? 3600,
    batteryCriticalMv: (i['battery_critical_mv'] as int?) ?? 3400,
    telegramConfigured: (i['telegram_configured'] as bool?) ?? false,
  );

  @override
  Future<Installation> installation() async =>
      _installation(_map(await _get('/installation')));

  @override
  Future<Installation> updateInstallation({
    String? name,
    String? timezone,
    int? batteryLowMv,
    int? batteryCriticalMv,
    String? telegramToken,
    String? telegramChatId,
  }) async {
    await _send('PATCH', '/installation', {
      'name': ?name,
      'timezone': ?timezone,
      'battery_low_mv': ?batteryLowMv,
      'battery_critical_mv': ?batteryCriticalMv,
      if (telegramToken != null || telegramChatId != null)
        'telegram': {'token': ?telegramToken, 'chat_id': ?telegramChatId},
    });
    return installation();
  }

  @override
  Future<GatewayStatus> gatewayStatus() async {
    final s = _map(await _get('/status'));
    final hub = _map(s['hub']);
    final gw = _map(s['gateway']);
    return GatewayStatus(
      hubOnline: (hub['online'] as bool?) ?? false,
      zigbee: (gw['zigbee2mqtt'] ?? 'unknown') as String,
      coordinator: gw['coordinator'] as String?,
      hubVersion: (hub['version'] ?? gw['hub_version']) as String?,
      apiVersion: _map(s['api'])['version'] as String?,
      clockSynced: gw['clock_synced'] as bool?,
      dbSizeBytes: _map(s['api'])['db_size'] as int?,
    );
  }

  @override
  Future<void> backup() => _send('POST', '/backup');

  @override
  Future<List<int>> exportData() async {
    final r = await _call(
      () => _dio.post<List<int>>('/export', options: Options(responseType: ResponseType.bytes)),
    );
    return (r as List).cast<int>();
  }

  // ---- plants and readings ---------------------------------------------------------------------

  @override
  Future<List<Plant>> plants() async {
    final results = await Future.wait([_get('/plants'), _get('/devices')]);
    final devices = {
      for (final d in _list(results[1]).cast<Map>()) d['id'] as String: d,
    };
    return [
      for (final p in _list(results[0]).cast<Map>()) _plant(p, devices),
    ];
  }

  /// The pump slot's `max_run_s` from the configuration the device runs; 0 when the plant has no pump.
  int _maxRun(Map p, Map<String, Map> devices) {
    final ref = _map(p['pump']);
    final dev = devices[ref['device_id']];
    if (dev == null) return 0;
    final cfg = _map(dev['reported_config']);
    for (final s in _list(cfg['slots']).cast<Map>()) {
      if (s['slot'] == ref['slot'] && s['module'] == 'pump') {
        return (s['max_run_s'] as int?) ?? 0;
      }
    }
    return 0;
  }

  SlotRef _ref(Object? v) {
    final m = _map(v);
    return SlotRef(deviceId: m['device_id'] as String?, slot: m['slot'] as int?);
  }

  Plant _plant(Map p, Map<String, Map> devices) => Plant(
    id: p['id'] as String,
    name: p['name'] as String,
    notes: (p['notes'] ?? '') as String,
    sensor: _ref(p['sensor']),
    pump: _ref(p['pump']),
    moisturePercent: (p['latest_value'] as num?)?.toDouble(),
    trend: switch (p['trend']) {
      'rising' => Trend.rising,
      'falling' => Trend.falling,
      _ => Trend.steady,
    },
    lastReadingAt: _dt(p['latest_ts']),
    maxRunS: _maxRun(p, devices),
  );

  Future<Plant> _plantAfterWrite(Map p) async {
    final devices = {
      for (final d in _list(await _get('/devices')).cast<Map>()) d['id'] as String: d,
    };
    return _plant(p, devices);
  }

  Map<String, Object?> _refJson(SlotRef r) => {'device_id': r.deviceId, 'slot': r.slot};

  @override
  Future<Plant> createPlant({
    required String name,
    SlotRef sensor = const SlotRef(),
    SlotRef pump = const SlotRef(),
    String notes = '',
  }) async => _plantAfterWrite(
    _map(
      await _send('POST', '/plants', {
        'name': name,
        'notes': notes,
        if (sensor.isSet) 'sensor': _refJson(sensor),
        if (pump.isSet) 'pump': _refJson(pump),
      }),
    ),
  );

  @override
  Future<Plant> updatePlant(
    String id, {
    String? name,
    String? notes,
    SlotRef? sensor,
    SlotRef? pump,
  }) async => _plantAfterWrite(
    _map(
      await _send('PATCH', '/plants/$id', {
        'name': ?name,
        'notes': ?notes,
        if (sensor != null) 'sensor': _refJson(sensor),
        if (pump != null) 'pump': _refJson(pump),
      }),
    ),
  );

  @override
  Future<void> deletePlant(String id) => _send('DELETE', '/plants/$id');

  static const _buckets = {
    ChartRange.day: 'raw',
    ChartRange.week: 'hour',
    ChartRange.month: 'hour',
    ChartRange.year: 'day',
  };

  @override
  Future<List<Reading>> readings(String plantId, ChartRange range) async {
    final end = _now().toUtc();
    final out = <Reading>[];
    String? cursor;
    for (var page = 0; page < 5; page++) {
      final r = _map(
        await _get('/plants/$plantId/readings', {
          'from': end.subtract(range.span).toIso8601String(),
          'to': end.toIso8601String(),
          'bucket': _buckets[range],
          'limit': 2000,
          'cursor': ?cursor,
        }),
      );
      for (final i in _list(r['items']).cast<Map>()) {
        final v = (i['avg'] ?? i['value']) as num?;
        if (v != null) out.add(Reading(_dt(i['ts'])!, v.toDouble()));
      }
      cursor = r['next_cursor'] as String?;
      if (cursor == null) break;
    }
    return out;
  }

  @override
  Future<void> calibrateBattery(String deviceId, int measuredMv) =>
      _send('POST', '/devices/$deviceId/battery/calibrate', {'measured_mv': measuredMv});

  @override
  Future<List<BatteryPoint>> batteryHistory(String deviceId, ChartRange range) async {
    final end = _now().toUtc();
    final out = <BatteryPoint>[];
    String? cursor;
    for (var page = 0; page < 5; page++) {
      final r = _map(
        await _get('/devices/$deviceId/health', {
          'from': end.subtract(range.span).toIso8601String(),
          'to': end.toIso8601String(),
          'limit': 1000,
          'cursor': ?cursor,
        }),
      );
      for (final i in _list(r['items']).cast<Map>()) {
        final mv = i['voltage_mv'] as int?;
        final at = _dt(i['ts']);
        if (mv != null && mv > 500 && at != null) out.add(BatteryPoint(at, mv));
      }
      cursor = r['next_cursor'] as String?;
      if (cursor == null) break;
    }
    out.sort((a, b) => a.at.compareTo(b.at));
    return out;
  }

  // ---- commands ----------------------------------------------------------------------------------

  Command _command(Map c) {
    final status = c['status'] as String;
    final delivered = c['delivered_at'] != null;
    final state = switch (status) {
      'queued' => CommandState.queued,
      'delivered' => CommandState.running,
      'cancelling' => delivered ? CommandState.running : CommandState.queued,
      'done' => CommandState.done,
      'failed' => CommandState.failed,
      'expired' => CommandState.expired,
      _ => CommandState.cancelled,
    };
    return Command(
      id: c['id'] as String,
      plantId: (c['plant_id'] ?? '') as String,
      deviceId: c['device_id'] as String,
      seconds: (_map(c['args'])['seconds'] as int?) ?? 0,
      state: state,
      createdAt: _dt(c['created_at'])!,
      cancelling: status == 'cancelling',
      sent: c['sent_at'] != null,
      expiresAt: _dt(c['exp']),
      runningUntil: _dt(c['ends_at']),
      finishedAt: _dt(c['finished_at']),
      failureReason: c['reason'] as String?,
      origin: c['source'] == 'rule' ? CommandOrigin.rule : CommandOrigin.user,
    );
  }

  @override
  Future<List<Command>> commands(String plantId) async {
    final r = _map(await _get('/plants/$plantId/commands', {'limit': 50}));
    return [
      for (final c in _list(r['items']).cast<Map>())
        if (c['action'] == 'pump.run') _command(c),
    ];
  }

  @override
  Future<Command> waterNow(String plantId, int seconds) async =>
      _command(_map(await _send('POST', '/plants/$plantId/water', {'seconds': seconds})));

  @override
  Future<void> cancelCommand(String commandId) =>
      _send('POST', '/commands/$commandId/cancel');

  // ---- rules ---------------------------------------------------------------------------------------

  Rule _rule(Map r) => Rule(
    id: r['id'] as String,
    plantId: r['plant_id'] as String,
    belowPercent: (r['threshold'] as num).round(),
    waterSeconds: r['water_s'] as int,
    cooldownS: r['cooldown_s'] as int,
    maxPerDay: r['max_per_day'] as int,
    enabled: r['enabled'] as bool,
    quietFrom: r['quiet_from'] as String?,
    quietTo: r['quiet_to'] as String?,
    notifyChannels: [for (final c in _list(r['notify_channels'])) c as String],
    notifyOn: [for (final c in _list(r['notify_on'])) c as String],
  );

  @override
  Future<List<Rule>> rules(String plantId) async => [
    for (final r in _list(await _get('/plants/$plantId/rules')).cast<Map>()) _rule(r),
  ];

  @override
  Future<Rule> saveRule(Rule rule) async {
    final base = '/plants/${rule.plantId}/rules';
    final body = {
      'enabled': rule.enabled,
      'threshold': rule.belowPercent,
      'water_s': rule.waterSeconds,
      'cooldown_s': rule.cooldownS,
      'max_per_day': rule.maxPerDay,
      'quiet_from': rule.quietFrom,
      'quiet_to': rule.quietTo,
      'notify_channels': rule.notifyChannels,
      'notify_on': rule.notifyOn,
    };
    final res = rule.id.isEmpty
        ? await _send('POST', base, body)
        : await _send('PATCH', '$base/${rule.id}', body);
    return _rule(_map(res));
  }

  @override
  Future<void> deleteRule(Rule rule) =>
      _send('DELETE', '/plants/${rule.plantId}/rules/${rule.id}');

  @override
  Future<List<RuleExecution>> ruleExecutions(String plantId, String ruleId) async {
    final r = _map(await _get('/plants/$plantId/rules/$ruleId/executions', {'limit': 30}));
    return [
      for (final e in _list(r['items']).cast<Map>())
        RuleExecution(
          at: _dt(e['ts'])!,
          decision: e['decision'] as String,
          skipReason: e['skip_reason'] as String?,
          commandId: e['command_id'] as String?,
        ),
    ];
  }

  // ---- devices ---------------------------------------------------------------------------------------

  static DeviceStatus _status(String? s) => switch (s) {
    'joining' => DeviceStatus.joining,
    'join_failed' => DeviceStatus.joinFailed,
    'unsupported' => DeviceStatus.unsupported,
    'ready' => DeviceStatus.ready,
    'online' => DeviceStatus.online,
    'late' => DeviceStatus.late,
    'safe_mode' => DeviceStatus.safeMode,
    _ => DeviceStatus.offline,
  };

  static ConfigSync _sync(String? s) => switch (s) {
    'in_sync' => ConfigSync.inSync,
    'rejected' => ConfigSync.rejected,
    _ => ConfigSync.pending,
  };

  DeviceConfigBody? _body(Object? v) {
    if (v is! Map) return null;
    return DeviceConfigBody(
      rev: (v['rev'] as int?) ?? 0,
      reportIntervalS: (v['report_interval_s'] as int?) ?? 300,
      fastReportIntervalS: (v['fast_report_interval_s'] as int?) ?? 30,
      fastReportHoldS: (v['fast_report_hold_s'] as int?) ?? 120,
      battLowMv: (v['batt_low_mv'] as int?) ?? 3500,
      slots: [
        for (final s in _list(v['slots']).cast<Map>())
          SlotConfig(
            slot: s['slot'] as int,
            module: s['module'] as String,
            port: s['port'] as String,
            calDry: (s['cal_dry'] as int?) ?? 3000,
            calWet: (s['cal_wet'] as int?) ?? 1200,
            samples: (s['samples'] as int?) ?? 16,
            maxRunS: (s['max_run_s'] as int?) ?? 60,
            minPauseS: (s['min_pause_s'] as int?) ?? 600,
            activeHigh: (s['active_high'] as bool?) ?? true,
          ),
      ],
    );
  }

  String? _configError(Object? e) {
    if (e is! Map) return null;
    final raw = e['raw'];
    return raw == null ? 'rejected' : 'rejected: $raw';
  }

  static const _batteryStates = {
    'absent': BatteryState.absent,
    'ok': BatteryState.ok,
    'low': BatteryState.low,
    'critical': BatteryState.critical,
  };

  Battery? _battery(Object? b) {
    if (b is! Map) return null;
    return Battery(
      state: _batteryStates[b['state']] ?? BatteryState.absent,
      mv: (b['mv'] as int?) ?? 0,
      percent: b['percent'] as int?,
      calibrated: (b['calibrated'] as bool?) ?? false,
      calPermille: (b['cal_permille'] as int?) ?? 1000,
    );
  }

  Device _device(Map d) {
    final reported = _body(d['reported_config']);
    return Device(
      id: d['id'] as String,
      name: ((d['name'] as String?)?.isNotEmpty ?? false) ? d['name'] as String : d['id'] as String,
      status: _status(d['status'] as String?),
      configSync: _sync(d['config_sync'] as String?),
      model: d['model'] as String?,
      board: d['board'] as String?,
      firmware: d['fw'] as String?,
      safeReason: d['safe_reason'] as String?,
      lastSeen: _dt(d['last_seen_at']),
      linkQuality: d['link_quality'] as int?,
      voltageMv: d['voltage_mv'] as int?,
      battery: _battery(d['battery']),
      desiredRev: (d['desired_rev'] as int?) ?? 0,
      reportedRev: d['reported_rev'] as int?,
      configError: _configError(d['config_error']),
      slots: reported?.slots ?? const [],
      diagnostics: (_map(d['diagnostics'])).cast<String, Object?>(),
    );
  }

  @override
  Future<List<Device>> devices() async => [
    for (final d in _list(await _get('/devices')).cast<Map>()) _device(d),
  ];

  @override
  Future<DeviceConfig> deviceConfig(String deviceId) async {
    final c = _map(await _get('/devices/$deviceId/config'));
    return DeviceConfig(
      desiredRev: (c['desired_rev'] as int?) ?? 0,
      reportedRev: c['reported_rev'] as int?,
      sync: _sync(c['sync_state'] as String?),
      desired: _body(c['desired']),
      reported: _body(c['reported']),
      error: _configError(c['error']),
      board: c['board'] as String?,
    );
  }

  @override
  Future<Board?> board(String name) async {
    try {
      final b = _map(await _get('/meta/boards/${Uri.encodeComponent(name)}'));
      return Board(
        name: b['name'] as String,
        ports: [
          for (final p in _list(b['ports']).cast<Map>())
            BoardPort(id: p['id'] as String, roles: [for (final r in _list(p['roles'])) r as String]),
        ],
      );
    } on ApiProblem catch (e) {
      if (e.status == 404) return null;
      rethrow;
    }
  }

  Map<String, Object?> _slotJson(SlotConfig s) => {
    'slot': s.slot,
    'module': s.module,
    'port': s.port,
    if (s.isPump) ...{
      'max_run_s': s.maxRunS,
      'min_pause_s': s.minPauseS,
      'active_high': s.activeHigh,
    } else ...{
      'cal_dry': s.calDry,
      'cal_wet': s.calWet,
      'samples': s.samples,
    },
  };

  @override
  Future<int> saveDeviceConfig(String deviceId, int baseRev, DeviceConfigBody config) async {
    final r = _map(
      await _send('PUT', '/devices/$deviceId/config', {
        'base_rev': baseRev,
        'config': {
          'report_interval_s': config.reportIntervalS,
          'fast_report_interval_s': config.fastReportIntervalS,
          'fast_report_hold_s': config.fastReportHoldS,
          'batt_low_mv': config.battLowMv,
          'slots': [for (final s in config.slots) _slotJson(s)],
        },
      }),
    );
    return r['rev'] as int;
  }

  @override
  Future<Device> renameDevice(String deviceId, String name) async =>
      _device(_map(await _send('PATCH', '/devices/$deviceId', {'name': name})));

  @override
  Future<void> deleteDevice(String deviceId, {bool force = false}) =>
      _send('DELETE', '/devices/$deviceId', null, force ? {'force': true} : null);

  @override
  Future<void> deviceAction(String deviceId, DeviceAction action) =>
      _send('POST', '/devices/$deviceId/actions', {
        'action': switch (action) {
          DeviceAction.identify => 'identify',
          DeviceAction.reboot => 'reboot',
          DeviceAction.clearSafeMode => 'clear_safe_mode',
          DeviceAction.reportNow => 'report_now',
        },
      });

  @override
  Future<List<Map<String, Object?>>> deviceEvents(String deviceId) async {
    final r = _map(await _get('/devices/$deviceId/events', {'limit': 50}));
    return [for (final e in _list(r['items']).cast<Map>()) e.cast<String, Object?>()];
  }

  JoinState _join(Object? v) {
    final j = _map(v);
    return JoinState(
      open: (j['open'] as bool?) ?? false,
      endsAt: _dt(j['ends_at']),
      deviceIds: [for (final d in _list(j['devices'])) d as String],
      error: j['error'] as String?,
    );
  }

  @override
  Future<JoinState> joinState() async => _join(await _get('/devices/join'));

  @override
  Future<JoinState> openJoin({String? installCode, int seconds = 120}) async =>
      _join(
        await _send('POST', '/devices/join', {
          'seconds': seconds,
          if (installCode != null && installCode.trim().isNotEmpty) 'install_code': installCode.trim(),
        }),
      );

  @override
  Future<void> closeJoin() => _send('DELETE', '/devices/join');

  // ---- alerts ---------------------------------------------------------------------------------------------

  static const _alertKinds = {
    'device_offline': AlertKind.deviceOffline,
    'battery_low': AlertKind.batteryLow,
    'battery_critical': AlertKind.batteryCritical,
    'sensor_error': AlertKind.sensorSuspect,
    'command_failed': AlertKind.commandFailed,
    'device_safe_mode': AlertKind.safeMode,
    'zigbee_offline': AlertKind.zigbeeOffline,
  };

  @override
  Future<List<Alert>> alerts() async => [
    for (final a in _list(await _get('/alerts')).cast<Map>())
      Alert(
        id: a['id'] as String,
        kind: _alertKinds[a['kind']] ?? AlertKind.other,
        kindName: a['kind'] as String,
        subject: (_map(a['subject'])['name'] ?? '') as String,
        createdAt: _dt(a['opened_at'])!,
        open: a['acked_at'] == null,
        critical: a['severity'] == 'critical',
        acknowledgedAt: _dt(a['acked_at']),
        acknowledgedBy: a['acked_by'] as String?,
      ),
  ];

  @override
  Future<void> acknowledgeAlert(String alertId) => _send('POST', '/alerts/$alertId/ack');

  // ---- live updates (SSE, App/specs.md Part A §6.2) -------------------------------------------------------

  static const _eventKinds = {
    'reading': LiveEventKind.reading,
    'plant': LiveEventKind.plant,
    'command': LiveEventKind.command,
    'device': LiveEventKind.device,
    'config': LiveEventKind.config,
    'alert': LiveEventKind.alert,
    'installation': LiveEventKind.installation,
    'join': LiveEventKind.join,
    'rule': LiveEventKind.rule,
    'notification': LiveEventKind.notification,
    'status': LiveEventKind.status,
    'resync': LiveEventKind.resync,
  };

  @override
  Stream<LiveEvent> events() {
    late final StreamController<LiveEvent> out;
    StreamSubscription<SseEvent>? sub;
    var closed = false;
    var attempt = 0;
    String? lastId;

    late final void Function() retry;

    Future<void> connect() async {
      if (closed) return;
      try {
        final ticket = _map(await _send('POST', '/events/ticket'))['ticket'];
        final url = _base.replace(
          path: '${_base.path}/api/v1/stream',
          queryParameters: {'ticket': ticket},
        );
        if (attempt > 0) out.add(const LiveEvent(LiveEventKind.resync));
        sub = connectSse(url, lastEventId: lastId).listen(
          (e) {
            attempt = 0;
            if (e.id != null && e.id!.isNotEmpty) lastId = e.id;
            final kind = _eventKinds[e.event];
            if (kind == null) return; // ping, hello
            String? entity, text;
            try {
              final data = jsonDecode(e.data);
              if (data is Map) {
                entity = (data['plant_id'] ?? data['device_id'] ?? data['id']) as String?;
                text = data['text'] as String?;
              }
            } on FormatException {
              // The payload is informational only.
            }
            out.add(LiveEvent(kind, entityId: entity, text: text));
          },
          onError: (_) => retry(),
          onDone: retry,
          cancelOnError: true,
        );
      } catch (_) {
        retry();
      }
    }

    retry = () {
      sub?.cancel();
      if (closed) return;
      // Backoff 1 s → 30 s, then a new ticket (App/specs.md Part A §6.2).
      final delay = Duration(seconds: attempt >= 5 ? 30 : 1 << attempt);
      attempt++;
      Timer(delay, connect);
    };

    out = StreamController<LiveEvent>.broadcast(
      onListen: connect,
      onCancel: () {
        closed = true;
        sub?.cancel();
      },
    );
    return out.stream;
  }
}
