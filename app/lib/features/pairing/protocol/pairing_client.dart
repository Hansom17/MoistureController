import 'dart:async';
import 'dart:typed_data';

import 'pairing_session.dart';

/// One BLE connection with notifications already enabled.
abstract class PairingTransport {
  /// Negotiated ATT MTU: writes are at most `mtu - 3` bytes.
  int get mtu;

  /// One ATT write (with response).
  Future<void> write(Uint8List data);

  /// The next notification; throws [TimeoutException] if none arrives in time.
  Future<Uint8List> read(Duration timeout);

  Future<void> close();
}

/// The device answered `ok: false` (contracts/ble.md §7.5).
class DeviceRequestException implements Exception {
  const DeviceRequestException(this.code, [this.detail = '']);

  final String code;
  final String detail;

  @override
  String toString() => detail.isEmpty ? code : '$code: $detail';
}

class WifiNetwork {
  const WifiNetwork(this.ssid, this.rssi, this.secure);

  final String ssid;
  final int rssi;
  final bool secure;
}

class DeviceInfo {
  const DeviceInfo({
    required this.hwMac,
    required this.firmware,
    required this.provisioned,
    this.deviceId,
  });

  final String hwMac;
  final String firmware;
  final bool provisioned;
  final String? deviceId;
}

class TestResult {
  const TestResult({required this.wifiOk, required this.mqttOk, this.detail = ''});

  final bool wifiOk;
  final bool mqttOk;
  final String detail;

  bool get ok => wifiOk && mqttOk;
}

/// What the wizard needs from a device (ble.md §7.5). [PairingClient] is the real one over BLE;
/// tests fake it.
abstract class PairingDevice {
  Future<void> open();
  Future<DeviceInfo> info();
  Future<List<WifiNetwork>> wifiScan();
  Future<void> setWifi(String ssid, String password);
  Future<void> setMqtt({
    required String deviceId,
    required String host,
    required int port,
    required String psk,
  });
  Future<TestResult> test();
  Future<void> commit();
  Future<void> abort();
  Future<void> close();
}

/// The operations of ble.md §7.5 over an open [PairingTransport].
class PairingClient implements PairingDevice {
  PairingClient(this._transport, Uint8List pop, {Uint8List? seed})
    : _session = PairingSession(pop: pop, seed: seed);

  final PairingTransport _transport;
  final PairingSession _session;
  var _nextId = 0;
  final _inbox = <Map<String, dynamic>>[];

  Future<void> _send(Uint8List data) async {
    for (final chunk in chunks(data, _transport.mtu)) {
      await _transport.write(chunk);
    }
  }

  Future<void> _pump(Duration timeout) async {
    final out = await _session.feed(await _transport.read(timeout));
    for (final f in out.frames) {
      await _send(f);
    }
    _inbox.addAll(out.messages);
  }

  /// The handshake. Throws [SessionException] (`wrongDeviceOrCode` for a failed confirmation).
  @override
  Future<void> open({Duration timeout = const Duration(seconds: 10)}) async {
    await _send(await _session.hello());
    while (!_session.isOpen) {
      await _pump(timeout);
    }
  }

  Future<Map<String, dynamic>> request(
    String op, {
    Map<String, dynamic> fields = const {},
    Duration timeout = const Duration(seconds: 15),
  }) async {
    final id = ++_nextId;
    await _send(await _session.seal({'id': id, 'op': op, ...fields}));
    while (true) {
      final i = _inbox.indexWhere((m) => m['id'] == id);
      if (i >= 0) {
        final msg = _inbox.removeAt(i);
        if (msg['ok'] != true) {
          throw DeviceRequestException(
            (msg['error'] as String?) ?? 'failed',
            (msg['detail'] as String?) ?? '',
          );
        }
        return msg;
      }
      await _pump(timeout);
    }
  }

  @override
  Future<DeviceInfo> info() async {
    final m = await request('info');
    return DeviceInfo(
      hwMac: m['hw_mac'] as String,
      firmware: m['fw'] as String,
      provisioned: m['provisioned'] as bool,
      deviceId: m['device_id'] as String?,
    );
  }

  @override
  Future<List<WifiNetwork>> wifiScan() async {
    final m = await request('wifi_scan', timeout: const Duration(seconds: 20));
    return [
      for (final n in (m['networks'] as List).cast<Map<String, dynamic>>())
        WifiNetwork(n['ssid'] as String, n['rssi'] as int, n['secure'] as bool),
    ];
  }

  @override
  Future<void> setWifi(String ssid, String password) =>
      request('set_wifi', fields: {'ssid': ssid, 'password': password});

  @override
  Future<void> setMqtt({
    required String deviceId,
    required String host,
    required int port,
    required String psk,
  }) => request(
    'set_mqtt',
    fields: {'device_id': deviceId, 'host': host, 'port': port, 'psk': psk},
  );

  /// Joins WiFi and connects to the broker; blocks for up to ~40 s.
  @override
  Future<TestResult> test() async {
    final m = await request('test', timeout: const Duration(seconds: 60));
    return TestResult(
      wifiOk: m['wifi'] == 'ok',
      mqttOk: m['mqtt'] == 'ok',
      detail: (m['detail'] as String?) ?? '',
    );
  }

  @override
  Future<void> commit() => request('commit');

  @override
  Future<void> abort() => request('abort');

  @override
  Future<void> close() => _transport.close();
}
