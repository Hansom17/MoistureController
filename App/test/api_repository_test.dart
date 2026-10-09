import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/data/models.dart';
import 'package:moisture_controller/data/repositories/api_moisture_repository.dart';

/// Answers with canned JSON, recorded from the real API (POST /households/{h}/devices, v2).
class CannedApi implements HttpClientAdapter {
  final requests = <String>[];

  static const device = {
    'id': 'mc-qta3x6zdk9w4zq3j',
    'name': 'Kitchen',
    'board': 'doit_esp32_devkit_v1',
    'status': 'new',
    'adapter': 'esp32-mqtt',
    'needs_repair': false,
    'fw': null,
    'batt_mv': null,
    'battery_percent': null,
    'rssi': null,
    'last_seen_at': null,
    'next_expected_at': null,
    'wake_interval_s': 600,
    'sync_state': 'pending',
    'desired_rev': 1,
    'reported_rev': 0,
    'config_error': null,
    'created_at': '2026-09-30T12:55:47.867375Z',
  };

  Object? answer(String method, String path) {
    if (method == 'POST' && path.endsWith('/devices')) {
      return {
        'device': device,
        'bundle': {
          'device_id': 'mc-qta3x6zdk9w4zq3j',
          'mqtt': {'host': '192.168.1.20', 'port': 8883, 'psk': 'ab' * 32},
        },
      };
    }
    if (method == 'POST' && path.endsWith('/rekey')) {
      return {
        'device_id': 'mc-qta3x6zdk9w4zq3j',
        'mqtt': {'host': '192.168.1.20', 'port': 8883, 'psk': 'cd' * 32},
      };
    }
    if (method == 'GET' && path.endsWith('/devices')) {
      return [
        device,
        {
          ...device,
          'id': 'mc-2',
          'needs_repair': true,
          'status': 'sleeping',
          'fw': '0.1.0',
        },
      ];
    }
    if (method == 'GET' && path.endsWith('/config')) {
      return {'desired': null, 'reported': null};
    }
    return null;
  }

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add('${options.method} ${options.path}');
    final body = answer(options.method, options.path);
    if (options.method == 'DELETE') return ResponseBody.fromString('', 204);
    return ResponseBody.fromString(
      jsonEncode(body),
      200,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late CannedApi api;
  late ApiMoistureRepository repo;

  setUp(() {
    api = CannedApi();
    repo = ApiMoistureRepository(
      baseUrl: 'http://api.test',
      token: () async => 'dev:test',
      httpAdapter: api,
    );
  });

  test(
    'createDevice understands a device that never connected (no firmware, no readings)',
    () async {
      final created = await repo.createDevice('h1', 'Kitchen');
      expect(created.device.id, 'mc-qta3x6zdk9w4zq3j');
      expect(
        created.device.state,
        DeviceState.offline,
      ); // `new` = never connected
      expect(created.device.firmware, '—');
      expect(created.device.gateway, GatewayLink.gateway);
      expect(created.device.needsRepair, isFalse);
      expect(created.bundle.deviceId, 'mc-qta3x6zdk9w4zq3j');
      expect(created.bundle.host, '192.168.1.20');
      expect(created.bundle.port, 8883);
      expect(created.bundle.psk, 'ab' * 32);
    },
  );

  test(
    'the device list maps needs_repair (the API has no `gateway` field any more)',
    () async {
      final devices = await repo.devices('h1');
      expect(devices.map((d) => d.needsRepair), [false, true]);
      expect(devices[1].state, DeviceState.sleeping);
    },
  );

  test('rekey and delete', () async {
    expect((await repo.rekeyDevice('h1', 'mc-1')).psk, 'cd' * 32);
    await repo.deleteDevice('h1', 'mc-1');
    expect(api.requests, contains('DELETE /households/h1/devices/mc-1'));
  });
}
