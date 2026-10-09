import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/api_problem.dart';
import 'package:moisture_controller/data/models.dart';
import 'package:moisture_controller/data/repositories/api_moisture_repository.dart';

/// Answers with canned JSON shaped like the gateway's api (Gateway/specs.md section 6) and records requests.
class CannedApi implements HttpClientAdapter {
  final requests = <RequestOptions>[];
  final bodies = <String, Object?>{};
  Object? Function(RequestOptions o)? respond;
  int failuresLeft = 0;

  static const pumpConfig = {
    'rev': 7,
    'report_interval_s': 300,
    'fast_report_interval_s': 30,
    'fast_report_hold_s': 120,
    'batt_low_mv': 3500,
    'slots': [
      {'slot': 0, 'module': 'moisture', 'port': 'P1', 'cal_dry': 3000, 'cal_wet': 1200, 'samples': 16},
      {'slot': 2, 'module': 'pump', 'port': 'P3', 'max_run_s': 45, 'min_pause_s': 600, 'active_high': true},
    ],
  };

  static const device = {
    'id': 'dev-abc',
    'ieee': '0x00124b0001',
    'name': 'Kitchen',
    'model': 'MC-PLANT',
    'fw': '0.1.0',
    'board': 'carrier-v1',
    'status': 'online',
    'safe_reason': null,
    'last_seen_at': '2026-10-09T20:00:00Z',
    'link_quality': 150,
    'voltage_mv': 0,
    'config_sync': 'pending',
    'desired_rev': 8,
    'reported_rev': 7,
    'desired_config': pumpConfig,
    'reported_config': pumpConfig,
    'config_error': null,
    'diagnostics': {'uptime_s': 3600, 'boot_reason': 'power_on'},
  };

  static const user = {
    'id': 'u1', 'username': 'phil', 'display_name': 'Phil', 'role': 'owner', 'created_at': '2026-10-01T00:00:00Z', 'disabled': false,
  };

  Object? answer(RequestOptions o) {
    final key = '${o.method} ${o.path}';
    switch (key) {
      case 'GET /meta':
        return {'name': 'Home', 'setup_required': false, 'version': '0.1.0', 'hub': {'online': true, 'compatible': true}};
      case 'POST /auth/login':
        return {'token': 'secret-token', 'token_id': 't1', 'user': user};
      case 'GET /me':
        return user;
      case 'GET /devices':
        return [device, {...device, 'id': 'dev-2', 'status': 'safe_mode', 'safe_reason': 'crash_loop', 'config_sync': 'in_sync'}];
      case 'GET /plants':
        return [
          {
            'id': 'p1', 'name': 'Ficus', 'notes': '', 'sensor': {'device_id': 'dev-abc', 'slot': 0},
            'pump': {'device_id': 'dev-abc', 'slot': 2}, 'latest_value': 41.5, 'latest_ts': '2026-10-09T20:00:00Z',
            'trend': 'falling', 'archived': false,
          },
          {'id': 'p2', 'name': 'Moss', 'sensor': {'device_id': null, 'slot': null}, 'pump': {'device_id': null, 'slot': null},
            'latest_value': null, 'latest_ts': null, 'trend': 'steady'},
        ];
      case 'GET /plants/p1/commands':
        return {
          'items': [
            _cmd('c1', 'delivered', ends: '2026-10-09T20:05:00Z'),
            _cmd('c2', 'cancelling', delivered: false),
            _cmd('c3', 'done', source: 'rule'),
            {..._cmd('c4', 'done'), 'action': 'pump.stop'},
          ],
          'next_cursor': null,
        };
      case 'GET /plants/p1/readings':
        return o.queryParameters['cursor'] == null
            ? {'items': [{'ts': '2026-10-09T10:00:00Z', 'avg': 40.0, 'min': 38.0, 'max': 42.0, 'count': 12}], 'next_cursor': 'abc'}
            : {'items': [{'ts': '2026-10-09T11:00:00Z', 'avg': 38.0, 'min': 37.0, 'max': 39.0, 'count': 12}], 'next_cursor': null};
      case 'GET /plants/p1/rules':
        return [
          {
            'id': 'r1', 'plant_id': 'p1', 'enabled': true, 'threshold': 30, 'water_s': 10, 'cooldown_s': 21600,
            'max_per_day': 2, 'quiet_from': '22:00', 'quiet_to': '07:00', 'notify_channels': ['app', 'telegram'],
            'notify_on': ['failed', 'watered'],
          },
        ];
      case 'PATCH /plants/p1/rules/r1':
        return {
          'id': 'r1', 'plant_id': 'p1', 'enabled': true, 'threshold': 25, 'water_s': 10, 'cooldown_s': 21600,
          'max_per_day': 2, 'quiet_from': null, 'quiet_to': null, 'notify_channels': ['app'], 'notify_on': ['failed'],
        };
      case 'GET /devices/join':
        return {'open': true, 'ends_at': '2026-10-09T20:02:00Z', 'devices': ['dev-new'], 'error': null};
      case 'POST /auth/reauth':
        return {'proof': 'proof-1', 'expires_in': 300};
      case 'POST /invites':
        return {'id': 'i1', 'role': 'member', 'status': 'open', 'expires_at': '2026-10-11T00:00:00Z', 'code': 'ABCDEFGH23456789JKLM', 'path': '/join#c=ABCDEFGH23456789JKLM'};
      case 'PUT /devices/dev-abc/config':
        return {'rev': 9};
      case 'GET /status':
        return {
          'api': {'version': '0.1.0', 'db_size': 73728},
          'hub': {'online': true, 'compatible': true, 'state': 'online', 'version': '0.1.0'},
          'gateway': {'zigbee2mqtt': 'offline', 'coordinator': 'unknown', 'clock_synced': true},
        };
    }
    return null;
  }

  static Map<String, Object?> _cmd(String id, String status, {String source = 'user', bool delivered = true, String? ends}) => {
    'id': id, 'device_id': 'dev-abc', 'plant_id': 'p1', 'action': 'pump.run', 'args': {'slot': 2, 'seconds': 10},
    'status': status, 'reason': null, 'source': source == 'user' ? 'manual' : 'rule', 'created_at': '2026-10-09T20:00:00Z',
    'exp': '2026-10-09T20:15:00Z', 'sent_at': '2026-10-09T20:00:01Z', 'delivered_at': delivered ? '2026-10-09T20:00:02Z' : null,
    'finished_at': null, 'ends_at': ends,
  };

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    requests.add(options);
    bodies['${options.method} ${options.path}'] = options.data;
    if (failuresLeft > 0) {
      failuresLeft--;
      throw DioException.connectionError(requestOptions: options, reason: 'down');
    }
    final body = respond?.call(options) ?? answer(options);
    if (body is _Status) {
      return ResponseBody.fromString(jsonEncode(body.body), body.code, headers: {
        Headers.contentTypeHeader: ['application/json'],
      });
    }
    return ResponseBody.fromString(jsonEncode(body ?? {}), 200, headers: {
      Headers.contentTypeHeader: ['application/json'],
    });
  }

  @override
  void close({bool force = false}) {}
}

class _Status {
  _Status(this.code, this.body);
  final int code;
  final Object body;
}

void main() {
  late CannedApi api;
  late ApiMoistureRepository repo;

  setUp(() {
    api = CannedApi();
    repo = ApiMoistureRepository(baseUrl: 'http://gw.local', httpAdapter: api, now: () => DateTime.utc(2026, 10, 9, 20));
  });

  RequestOptions last(String method, String path) =>
      api.requests.lastWhere((r) => r.method == method && r.path == path);

  test('sign-in: the token is sent on later requests and the user is parsed', () async {
    final session = await repo.login(username: 'phil', password: 'pw', deviceName: 'Laptop');
    expect(session.token, 'secret-token');
    expect(session.user.role, Role.owner);
    expect(api.bodies['POST /auth/login'], {'username': 'phil', 'password': 'pw', 'device_name': 'Laptop'});
    expect(last('POST', '/auth/login').headers['Authorization'], isNull);
    repo.useToken(session.token);
    await repo.me();
    expect(last('GET', '/me').headers['Authorization'], 'Bearer secret-token');
    expect(last('GET', '/me').headers['X-MC-App'], isNotNull);
  });

  test('meta before sign-in', () async {
    final m = await repo.meta();
    expect(m.name, 'Home');
    expect(m.setupRequired, isFalse);
    expect(m.hubOnline, isTrue);
  });

  test('devices: status, safe mode, config sync, slots from the running configuration', () async {
    final list = await repo.devices();
    final d = list.first;
    expect(d.name, 'Kitchen');
    expect(d.status, DeviceStatus.online);
    expect(d.configSync, ConfigSync.pending);
    expect(d.desiredRev, 8);
    expect(d.reportedRev, 7);
    expect(d.lastSeen, DateTime.utc(2026, 10, 9, 20).toLocal());
    expect(d.slots.map((s) => s.module), ['moisture', 'pump']);
    expect(d.slots.last.maxRunS, 45);
    expect(d.diagnostics['uptime_s'], 3600);
    expect(list.last.status, DeviceStatus.safeMode);
    expect(list.last.safeReason, 'crash_loop');
  });

  test('plants: moisture, trend and the pump limit come from the device configuration', () async {
    final plants = await repo.plants();
    expect(plants.first.moisturePercent, 41.5);
    expect(plants.first.trend, Trend.falling);
    expect(plants.first.maxRunS, 45);
    expect(plants.first.hasPump, isTrue);
    expect(plants.first.pump.deviceId, 'dev-abc');
    expect(plants.last.hasPump, isFalse);
    expect(plants.last.moisturePercent, isNull);
    expect(plants.last.trend, Trend.steady);
  });

  test('commands: only watering runs, running and cancelling states, origin', () async {
    final list = await repo.commands('p1');
    expect(list.map((c) => c.id), ['c1', 'c2', 'c3']);
    expect(list[0].state, CommandState.running);
    expect(list[0].runningUntil, isNotNull);
    expect(list[1].state, CommandState.queued);
    expect(list[1].cancelling, isTrue);
    expect(list[2].origin, CommandOrigin.rule);
    expect(list[0].seconds, 10);
    expect(list[0].deviceId, 'dev-abc');
  });

  test('readings: hourly buckets for a week, all pages are followed', () async {
    final r = await repo.readings('p1', ChartRange.week);
    expect(r.map((x) => x.moisturePercent), [40.0, 38.0]);
    final first = api.requests.firstWhere((x) => x.path == '/plants/p1/readings');
    expect(first.queryParameters['bucket'], 'hour');
    expect(first.queryParameters['from'], startsWith('2026-10-02T20'));
    expect(api.requests.where((x) => x.path == '/plants/p1/readings'), hasLength(2));
  });

  test('rules: cooldown, daily limit, quiet hours and notification settings', () async {
    final r = (await repo.rules('p1')).single;
    expect(r.belowPercent, 30);
    expect(r.cooldownHours, 6);
    expect(r.maxPerDay, 2);
    expect(r.quietFrom, '22:00');
    expect(r.notifyChannels, ['app', 'telegram']);
    await repo.saveRule(r.copyWith(belowPercent: 25, clearQuiet: true));
    final body = api.bodies['PATCH /plants/p1/rules/r1'] as Map;
    expect(body['threshold'], 25);
    expect(body['quiet_from'], isNull);
    expect(body['cooldown_s'], 21600);
  });

  test('errors become ApiProblem with the stable code, unreachable and unauthorized are reported', () async {
    api.respond = (o) => o.path == '/plants/p1/water' ? _Status(409, {'code': 'busy', 'detail': 'Pump is busy'}) : null;
    await expectLater(
      repo.waterNow('p1', 5),
      throwsA(isA<ApiProblem>().having((p) => p.type, 'type', ApiProblem.busy).having((p) => p.status, 'status', 409)),
    );

    var unauthorized = 0;
    repo.onUnauthorized = () => unauthorized++;
    api.respond = (o) => _Status(401, {'code': 'unauthorized'});
    await expectLater(repo.me(), throwsA(isA<ApiProblem>()));
    expect(unauthorized, 1);

    api.respond = (o) => _Status(401, {'code': 'reauth_required'});
    await expectLater(repo.deleteDevice('dev-abc'), throwsA(isA<ApiProblem>().having((p) => p.type, 'type', 'reauth_required')));
    expect(unauthorized, 1); // reauth_required is not a lost login

    api.respond = null;
    var unreachable = 0;
    repo.onUnreachable = () => unreachable++;
    api.failuresLeft = 10;
    await expectLater(repo.plants(), throwsA(isA<ApiProblem>().having((p) => p.type, 'type', ApiProblem.network)));
    expect(unreachable, greaterThan(0));
  });

  test('GETs are retried with backoff, writes are not', () async {
    api.failuresLeft = 2;
    expect(await repo.meta(), isNotNull); // third attempt succeeds
    expect(api.requests.where((r) => r.path == '/meta'), hasLength(3));

    api.requests.clear();
    api.failuresLeft = 1;
    await expectLater(repo.waterNow('p1', 5), throwsA(isA<ApiProblem>()));
    expect(api.requests.where((r) => r.path == '/plants/p1/water'), hasLength(1));
  });

  test('reauth: the proof is sent on later requests, until it runs out', () async {
    var now = DateTime.utc(2026, 10, 9, 20);
    repo = ApiMoistureRepository(baseUrl: 'http://gw.local', httpAdapter: api, now: () => now);
    await repo.me();
    expect(last('GET', '/me').headers['X-MC-Reauth'], isNull);
    await repo.reauth('pw');
    await repo.deleteDevice('dev-abc');
    expect(last('DELETE', '/devices/dev-abc').headers['X-MC-Reauth'], 'proof-1');
    now = now.add(const Duration(minutes: 6));
    await repo.me();
    expect(last('GET', '/me').headers['X-MC-Reauth'], isNull);
  });

  test('saving a configuration sends the api format with the base revision', () async {
    final body = DeviceConfigBody(
      reportIntervalS: 120,
      slots: const [
        SlotConfig(slot: 0, module: 'moisture', port: 'P1', calDry: 2900, calWet: 1100),
        SlotConfig(slot: 2, module: 'pump', port: 'P3', maxRunS: 20, minPauseS: 300, activeHigh: false),
      ],
    );
    expect(await repo.saveDeviceConfig('dev-abc', 8, body), 9);
    final sent = api.bodies['PUT /devices/dev-abc/config'] as Map;
    expect(sent['base_rev'], 8);
    final cfg = sent['config'] as Map;
    expect(cfg['report_interval_s'], 120);
    expect((cfg['slots'] as List)[0], {'slot': 0, 'module': 'moisture', 'port': 'P1', 'cal_dry': 2900, 'cal_wet': 1100, 'samples': 16});
    expect((cfg['slots'] as List)[1], {'slot': 2, 'module': 'pump', 'port': 'P3', 'max_run_s': 20, 'min_pause_s': 300, 'active_high': false});
  });

  test('join window and invites', () async {
    final j = await repo.joinState();
    expect(j.open, isTrue);
    expect(j.deviceIds, ['dev-new']);
    expect(j.endsAt, isNotNull);
    await repo.openJoin(installCode: ' 83FE D340 ', seconds: 60);
    expect(api.bodies['POST /devices/join'], {'seconds': 60, 'install_code': '83FE D340'});

    final created = await repo.createInvite(Role.member);
    expect(created.code, 'ABCDEFGH23456789JKLM');
    expect(created.link('http://gw.local'), 'http://gw.local/join#c=ABCDEFGH23456789JKLM');
    expect(created.invite.role, Role.member);
  });

  test('gateway status: Zigbee down is detected', () async {
    final s = await repo.gatewayStatus();
    expect(s.hubOnline, isTrue);
    expect(s.zigbeeDown, isTrue);
    expect(s.dbSizeBytes, 73728);
  });

  test('delete a device with force', () async {
    await repo.deleteDevice('dev-abc', force: true);
    expect(last('DELETE', '/devices/dev-abc').queryParameters['force'], true);
  });
}
