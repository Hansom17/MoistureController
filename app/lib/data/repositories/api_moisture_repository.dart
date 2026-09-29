import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import '../api/sse.dart';
import '../api_problem.dart';
import '../models.dart';
import 'moisture_repository.dart';

/// Talks to the API server (`/api/v1`, Api_Specs §6).
///
/// Hand-written until the Dart client is generated from contracts/api.yaml
/// (App_Specs §2); it maps the API's JSON onto the app's models.
class ApiMoistureRepository implements MoistureRepository {
  ApiMoistureRepository({
    required String baseUrl,
    required Future<String> Function() token,
    String appHeader = 'dev/0.1.0',
  }) : _base = Uri.parse(baseUrl),
       _dio = Dio(
         BaseOptions(
           baseUrl: '$baseUrl/api/v1',
           connectTimeout: const Duration(seconds: 10),
           receiveTimeout: const Duration(seconds: 20),
           headers: {'X-MC-App': appHeader},
         ),
       ) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          options.headers['Authorization'] = 'Bearer ${await token()}';
          handler.next(options);
        },
      ),
    );
  }

  final Uri _base;
  final Dio _dio;

  /// Last known `next_expected_at` per device, for "device expected ~14:32".
  final _nextExpected = <String, DateTime>{};

  Future<dynamic> _get(String path, [Map<String, dynamic>? query]) =>
      _call(() => _dio.get(path, queryParameters: query));

  Future<dynamic> _send(String method, String path, [Object? body]) => _call(
    () => _dio.request(
      path,
      data: body,
      options: Options(method: method),
    ),
  );

  Future<dynamic> _call(Future<Response<dynamic>> Function() request) async {
    try {
      return (await request()).data;
    } on DioException catch (e) {
      final data = e.response?.data;
      if (data is Map && data['type'] is String) {
        throw ApiProblem(
          data['type'] as String,
          status: e.response?.statusCode ?? 0,
          detail: data['detail'] as String?,
        );
      }
      throw ApiProblem(
        'network',
        status: e.response?.statusCode ?? 0,
        detail: e.message,
      );
    }
  }

  static DateTime? _dt(Object? v) =>
      v == null ? null : DateTime.parse(v as String).toLocal();

  // --- households ------------------------------------------------------------

  @override
  Future<List<Household>> households() async {
    final list = await _get('/me/households') as List;
    return [
      for (final h in list.cast<Map>())
        Household(
          id: h['id'] as String,
          name: h['name'] as String,
          timezone: h['timezone'] as String,
          role: Role.values.byName(h['role'] as String),
          gateway: h['gateway'] == null
              ? null
              : GatewayStatus(
                  online: h['gateway']['online'] as bool,
                  offlineSince: _dt(h['gateway']['offline_since']),
                ),
        ),
    ];
  }

  // --- plants and readings ----------------------------------------------------

  @override
  Future<List<Plant>> plants(String householdId) async {
    final list = await _get('/households/$householdId/plants') as List;
    return [for (final p in list.cast<Map>()) _plant(p)];
  }

  Plant _plant(Map p) => Plant(
    id: p['id'] as String,
    name: p['name'] as String,
    deviceId: (p['sensor_device_id'] ?? p['pump_device_id'] ?? '') as String,
    moisturePercent: (p['moisture'] as num?)?.toDouble(),
    trend: Trend.values.byName(p['trend'] as String),
    lastReadingAt: _dt(p['last_reading_at']),
    maxRunS: (p['max_run_s'] as int?) ?? 0,
  );

  static const _buckets = {
    ChartRange.day: 'raw',
    ChartRange.week: '1h',
    ChartRange.month: '1h',
    ChartRange.year: '1d',
  };

  @override
  Future<List<Reading>> readings(
    String householdId,
    String plantId,
    ChartRange range,
  ) async {
    final end = DateTime.now().toUtc();
    final list =
        await _get('/households/$householdId/plants/$plantId/readings', {
              'start': end.subtract(range.span).toIso8601String(),
              'end': end.toIso8601String(),
              'bucket': _buckets[range],
            })
            as List;
    return [
      for (final r in list.cast<Map>())
        if (r['value'] != null)
          Reading(_dt(r['ts'])!, (r['value'] as num).toDouble()),
    ];
  }

  // --- commands -----------------------------------------------------------------

  Command _command(Map c) {
    final state = switch (c['state'] as String) {
      'queued' || 'cancelling' => CommandState.queued,
      'delivered' => CommandState.delivered,
      'running' => CommandState.running,
      'done' => CommandState.done,
      'failed' => CommandState.failed,
      'expired' => CommandState.expired,
      _ => CommandState.cancelled,
    };
    final createdAt = _dt(c['created_at'])!;
    final origin = switch (c['source']) {
      'rule' => CommandOrigin.rule,
      'local' => CommandOrigin.local,
      _ => CommandOrigin.user,
    };
    return Command(
      id: c['id'] as String,
      plantId: (c['plant_id'] ?? '') as String,
      seconds: (c['seconds'] as int?) ?? 0,
      state: state,
      createdAt: createdAt,
      expectedAt: _nextExpected[c['device_id']] ?? createdAt,
      runningUntil: _dt(c['ends_at']),
      finishedAt: _dt(c['finished_at']),
      failureReason: c['reason'] as String?,
      origin: origin,
    );
  }

  @override
  Future<List<Command>> commands(String householdId, String plantId) async {
    final list =
        await _get('/households/$householdId/plants/$plantId/commands') as List;
    return [for (final c in list.cast<Map>()) _command(c)];
  }

  @override
  Future<Command> waterNow(
    String householdId,
    String plantId,
    int seconds,
  ) async {
    final res =
        await _send('POST', '/households/$householdId/plants/$plantId/water', {
              'seconds': seconds,
            })
            as Map;
    return _command(res['command'] as Map);
  }

  @override
  Future<void> cancelCommand(String householdId, String commandId) =>
      _send('POST', '/households/$householdId/commands/$commandId/cancel');

  // --- rules ----------------------------------------------------------------------

  Rule _rule(Map r) => Rule(
    id: r['id'] as String,
    plantId: r['plant_id'] as String,
    belowPercent: (r['threshold'] as num).round(),
    waterSeconds: r['water_s'] as int,
    minIntervalHours: ((r['cooldown_s'] as int) / 3600).round(),
    enabled: r['enabled'] as bool,
  );

  @override
  Future<List<Rule>> rules(String householdId, String plantId) async {
    final list =
        await _get('/households/$householdId/plants/$plantId/rules') as List;
    return [for (final r in list.cast<Map>()) _rule(r)];
  }

  @override
  Future<Rule> saveRule(String householdId, Rule rule) async {
    final base = '/households/$householdId/plants/${rule.plantId}/rules';
    final body = {
      'enabled': rule.enabled,
      'threshold': rule.belowPercent,
      'water_s': rule.waterSeconds,
      'cooldown_s': rule.minIntervalHours * 3600,
    };
    final res = rule.id.isEmpty
        ? await _send('POST', base, body)
        : await _send('PATCH', '$base/${rule.id}', body);
    return _rule(res as Map);
  }

  @override
  Future<void> deleteRule(String householdId, Rule rule) => _send(
    'DELETE',
    '/households/$householdId/plants/${rule.plantId}/rules/${rule.id}',
  );

  // --- devices --------------------------------------------------------------------

  @override
  Future<List<Device>> devices(String householdId) async {
    final list = (await _get('/households/$householdId/devices') as List)
        .cast<Map>();
    final configs = await Future.wait([
      for (final d in list)
        _get('/households/$householdId/devices/${d['id']}/config'),
    ]);
    return [for (final (i, d) in list.indexed) _device(d, configs[i] as Map)];
  }

  Device _device(Map d, Map config) {
    final created = _dt(d['created_at'])!;
    final next = _dt(d['next_expected_at']);
    if (next != null) _nextExpected[d['id'] as String] = next;
    final slots =
        ((config['reported'] ?? config['desired'])?['slots'] ?? []) as List;
    final error = d['config_error'] as Map?;
    return Device(
      id: d['id'] as String,
      name: d['name'] as String,
      board: d['board'] as String,
      firmware: (d['fw'] ?? '—') as String,
      batteryPercent: (d['battery_percent'] as int?) ?? 0,
      rssi: (d['rssi'] as int?) ?? 0,
      state: switch (d['status'] as String) {
        'online' || 'service' => DeviceState.online,
        'sleeping' => DeviceState.sleeping,
        'late' => DeviceState.late,
        _ => DeviceState.offline, // offline, or `new` = never connected
      },
      lastSeen: _dt(d['last_seen_at']) ?? created,
      nextExpectedAt: next ?? created,
      wakeIntervalS: d['wake_interval_s'] as int,
      configSync: switch (d['sync_state'] as String) {
        'in_sync' => ConfigSync.inSync,
        'rejected' => ConfigSync.rejected,
        _ => ConfigSync.pending,
      },
      configRev: d['reported_rev'] as int,
      configError: error == null
          ? null
          : (error['detail'] ?? error['code']) as String?,
      gateway: GatewayLink.values.byName(d['gateway'] as String),
      slots: [
        for (final s in slots.cast<Map>())
          Slot(
            index: s['slot'] as int,
            module: s['module'] as String,
            pin: (s['pin'] ?? s['addr'] ?? 0) as int,
            maxRunS: s['max_run_s'] as int?,
          ),
      ],
    );
  }

  @override
  Future<void> deviceAction(
    String householdId,
    String deviceId,
    DeviceAction action,
  ) => _send('POST', '/households/$householdId/devices/$deviceId/actions', {
    'action': switch (action) {
      DeviceAction.identify => 'identify',
      DeviceAction.serviceMode => 'service',
      DeviceAction.reboot => 'reboot',
    },
  });

  // --- alerts ---------------------------------------------------------------------

  static const _alertKinds = {
    'device_offline': AlertKind.deviceOffline,
    'device_crashed': AlertKind.deviceOffline,
    'battery_low': AlertKind.batteryLow,
    'sensor_error': AlertKind.sensorSuspect,
    'command_failed': AlertKind.commandFailed,
  };

  @override
  Future<List<Alert>> alerts(String householdId) async {
    final list = await _get('/households/$householdId/alerts') as List;
    return [
      for (final a in list.cast<Map>())
        Alert(
          id: a['id'] as String,
          kind: _alertKinds[a['kind']] ?? AlertKind.other,
          kindName: a['kind'] as String,
          subject: (a['subject_name'] ?? '') as String,
          createdAt: _dt(a['opened_at'])!,
          open: a['resolved_at'] == null,
          acknowledgedAt: _dt(a['acked_at']),
        ),
    ];
  }

  @override
  Future<void> acknowledgeAlert(String householdId, String alertId) =>
      _send('POST', '/households/$householdId/alerts/$alertId/ack');

  // --- gateway (App_Specs §12) -------------------------------------------------------------

  GatewayInfo _gateway(Map h) => GatewayInfo(
    id: h['id'] as String,
    status: h['status'] as String,
    online: h['online'] as bool,
    inSync: h['in_sync'] as bool,
    offlineSince: _dt(h['offline_since']),
    version: h['version'] as String?,
    latestVersion: h['latest_version'] as String?,
    arch: h['arch'] as String?,
    adapters: [
      for (final a in (h['adapters'] as List? ?? const [])) a as String,
    ],
    outboxDepth: h['outbox_depth'] as int?,
    timeSynced: h['time_synced'] as bool?,
    lanHost: h['lan_host'] as String?,
    lanPort: (h['lan_port'] as int?) ?? 8883,
    lanHostOverride: h['lan_host_override'] as String?,
    lastStateAt: _dt(h['last_state_at']),
  );

  @override
  Future<GatewayInfo?> gateway(String householdId) async {
    try {
      return _gateway(await _get('/households/$householdId/gateway') as Map);
    } on ApiProblem catch (e) {
      if (e.status == 404) return null;
      rethrow;
    }
  }

  @override
  Future<GatewayInfo> claimGateway(String householdId, String userCode) async =>
      _gateway(
        await _send('POST', '/households/$householdId/gateway', {
              'user_code': userCode.trim(),
            })
            as Map,
      );

  @override
  Future<GatewayInfo> setGatewayLanHost(
    String householdId,
    String? lanHostOverride,
  ) async => _gateway(
    await _send('PATCH', '/households/$householdId/gateway', {
          'lan_host_override': lanHostOverride,
        })
        as Map,
  );

  @override
  Future<void> removeGateway(String householdId) =>
      _send('DELETE', '/households/$householdId/gateway');

  // --- live updates (SSE, App_Specs §6.2) --------------------------------------------

  static const _eventKinds = {
    'reading': LiveEventKind.reading,
    'plant': LiveEventKind.reading,
    'command': LiveEventKind.command,
    'device': LiveEventKind.device,
    'config': LiveEventKind.config,
    'alert': LiveEventKind.alert,
    'gateway': LiveEventKind.gateway,
    'household': LiveEventKind.household,
    'rule': LiveEventKind.rule,
    'rule_execution': LiveEventKind.rule,
    'resync': LiveEventKind.resync,
  };

  @override
  Stream<LiveEvent> events(String householdId) {
    late final StreamController<LiveEvent> out;
    StreamSubscription<SseEvent>? sub;
    var closed = false;
    var attempt = 0;
    String? lastId;

    late final void Function() retry;

    Future<void> connect() async {
      if (closed) return;
      try {
        final ticket = (await _send('POST', '/events/ticket') as Map)['ticket'];
        final url = _base.replace(
          path: '${_base.path}/api/v1/households/$householdId/stream',
          queryParameters: {'ticket': ticket},
        );
        if (attempt > 0) out.add(const LiveEvent(LiveEventKind.resync));
        sub = connectSse(url, lastEventId: lastId).listen(
          (e) {
            attempt = 0;
            if (e.id != null && e.id!.isNotEmpty) lastId = e.id;
            final kind = _eventKinds[e.event];
            if (kind == null) return; // ping
            String? entity;
            try {
              final data = jsonDecode(e.data);
              if (data is Map) {
                entity = (data['plant_id'] ?? data['id']) as String?;
              }
            } on FormatException {
              // Payload is informational only.
            }
            out.add(LiveEvent(kind, entityId: entity));
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
      // Backoff 1 s → 30 s, then a new ticket (App_Specs §6.2).
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
