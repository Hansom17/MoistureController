import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/core/session.dart';
import 'package:moisture_controller/data/repositories/fake_moisture_repository.dart';
import 'package:moisture_controller/features/pairing/pairing_controller.dart';
import 'package:moisture_controller/features/pairing/protocol/pairing_client.dart';
import 'package:moisture_controller/features/pairing/protocol/pairing_label.dart';
import 'package:moisture_controller/features/pairing/protocol/pairing_session.dart';
import 'package:moisture_controller/features/pairing/protocol/pairing_transport.dart';

final label = PairingLabel('MC-26EA', Uint8List.fromList(List.generate(16, (i) => i)));

/// A device that does what the firmware does, at the level the wizard sees it.
class FakeDevice implements PairingDevice {
  FakeDevice({this.wifiOk = true, this.mqttOk = true, this.openError});

  bool wifiOk, mqttOk;
  Object? openError;
  final calls = <String>[];
  String? ssid, password;
  Map<String, Object?>? mqtt;
  var committed = false, aborted = false, closed = false;

  @override
  Future<void> open() async {
    calls.add('open');
    if (openError != null) throw openError!;
  }

  @override
  Future<DeviceInfo> info() async {
    calls.add('info');
    return const DeviceInfo(hwMac: '24:6F:28:AA:BB:CC', firmware: '0.1.0', provisioned: false);
  }

  @override
  Future<List<WifiNetwork>> wifiScan() async {
    calls.add('wifi_scan');
    return const [WifiNetwork('Home', -50, true), WifiNetwork('Guest', -70, false)];
  }

  @override
  Future<void> setWifi(String ssid, String password) async {
    calls.add('set_wifi');
    this.ssid = ssid;
    this.password = password;
  }

  @override
  Future<void> setMqtt({
    required String deviceId,
    required String host,
    required int port,
    required String psk,
  }) async {
    calls.add('set_mqtt');
    mqtt = {'device_id': deviceId, 'host': host, 'port': port, 'psk': psk};
  }

  @override
  Future<TestResult> test() async {
    calls.add('test');
    return TestResult(
      wifiOk: wifiOk,
      mqttOk: mqttOk,
      detail: mqttOk ? '' : 'broker: error -5',
    );
  }

  @override
  Future<void> commit() async {
    calls.add('commit');
    committed = true;
  }

  @override
  Future<void> abort() async {
    calls.add('abort');
    aborted = true;
  }

  @override
  Future<void> close() async => closed = true;
}

({ProviderContainer container, FakeMoistureRepository repo, FakeDevice device}) setup({
  FakeDevice? device,
  Object? connectError,
  String household = 'h1',
}) {
  final repo = FakeMoistureRepository(latency: Duration.zero);
  final dev = device ?? FakeDevice();
  final container = ProviderContainer(
    overrides: [
      repositoryProvider.overrideWithValue(repo),
      pairingConnectorProvider.overrideWithValue((label) async {
        if (connectError != null) throw connectError;
        return dev;
      }),
      pairingPollIntervalProvider.overrideWithValue(const Duration(milliseconds: 5)),
      pairingOnlineTimeoutProvider.overrideWithValue(const Duration(milliseconds: 200)),
    ],
  );
  addTearDown(container.dispose);
  addTearDown(repo.dispose);
  return (container: container, repo: repo, device: dev);
}

Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 20));

void main() {
  const h = 'h1';
  PairingState read(ProviderContainer c) => c.read(pairingControllerProvider(h));
  // the wizard screen keeps the (autoDispose) controller alive by watching it: so do the tests
  PairingController ctl(ProviderContainer c) {
    c.listen(pairingControllerProvider(h), (_, _) {});
    return c.read(pairingControllerProvider(h).notifier);
  }

  test('the happy path: create, connect, scan, test, commit, online, done', () async {
    final t = setup();
    final c = ctl(t.container)..setLabel(label);
    expect(read(t.container).step, PairingStep.name);

    await c.begin('Kitchen');
    var s = read(t.container);
    expect(s.step, PairingStep.wifi);
    expect(s.networks.map((n) => n.ssid), ['Home', 'Guest']);
    expect(s.deviceId, isNotNull);
    expect(t.device.calls, ['open', 'info', 'wifi_scan']);

    final devices = await t.repo.devices(h);
    expect(devices.any((d) => d.id == s.deviceId && d.name == 'Kitchen'), isTrue);

    // the device comes online shortly after the commit
    Timer(const Duration(milliseconds: 30), () => t.repo.simulateDeviceOnline(h, s.deviceId!));
    await c.submitWifi('Home', 'secret');
    s = read(t.container);
    expect(s.step, PairingStep.done);
    expect(s.stillWaiting, isFalse);
    expect(t.device.ssid, 'Home');
    expect(t.device.password, 'secret');
    expect(t.device.mqtt!['device_id'], s.deviceId);
    expect(t.device.mqtt!['psk'], 'ab' * 32);
    expect(t.device.calls.skip(3), ['set_wifi', 'set_mqtt', 'test', 'commit']);
    expect(t.device.closed, isTrue);
  });

  test('a failed test returns to the WiFi step, keeps the connection and allows a retry', () async {
    final t = setup(device: FakeDevice(mqttOk: false));
    final c = ctl(t.container)..setLabel(label);
    await c.begin('Kitchen');
    await c.submitWifi('Home', 'wrong');
    var s = read(t.container);
    expect(s.step, PairingStep.wifi);
    expect(s.testError!.wifiOk, isTrue);
    expect(s.testError!.mqttOk, isFalse);
    expect(s.testError!.detail, contains('broker'));
    expect(t.device.committed, isFalse);
    expect(t.device.closed, isFalse, reason: 'still connected for the next try');

    t.device.mqttOk = true;
    Timer(const Duration(milliseconds: 30), () => t.repo.simulateDeviceOnline(h, s.deviceId!));
    await c.submitWifi('Home', 'right');
    expect(read(t.container).step, PairingStep.done);
    expect(t.device.committed, isTrue);
  });

  test('done with stillWaiting when the device does not show up in time', () async {
    final t = setup();
    final c = ctl(t.container)..setLabel(label);
    await c.begin('Kitchen');
    await c.submitWifi('Home', 'x');
    final s = read(t.container);
    expect(s.step, PairingStep.done);
    expect(s.stillWaiting, isTrue);
    expect(t.device.committed, isTrue);
  });

  test('no gateway / gateway offline are reported before touching the device', () async {
    final t = setup();
    // household h2's gateway is offline in the demo data, and the role is viewer: use a
    // household without a gateway instead
    await t.repo.removeGateway(h);
    final c = ctl(t.container)..setLabel(label);
    await c.begin('Kitchen');
    var s = read(t.container);
    expect(s.step, PairingStep.failed);
    expect(s.failure, PairingFailure.noGateway);
    expect(t.device.calls, isEmpty);
  });

  test('a wrong code deletes the record and says so', () async {
    final t = setup(device: FakeDevice(openError: const SessionException('confirm_failed')));
    final c = ctl(t.container)..setLabel(label);
    final before = (await t.repo.devices(h)).length;
    await c.begin('Kitchen');
    final s = read(t.container);
    expect(s.step, PairingStep.failed);
    expect(s.failure, PairingFailure.wrongCode);
    expect(s.canRetry, isFalse);
    expect((await t.repo.devices(h)).length, before, reason: 'the record was taken back');
  });

  test('device not found keeps the record and can be retried', () async {
    final t = setup(connectError: const DeviceNotFoundException('MC-26EA'));
    final c = ctl(t.container)..setLabel(label);
    final before = (await t.repo.devices(h)).length;
    await c.begin('Kitchen');
    var s = read(t.container);
    expect(s.failure, PairingFailure.notFound);
    expect(s.canRetry, isTrue);
    expect((await t.repo.devices(h)).length, before + 1, reason: 'kept for the retry');
    // the retry finds it this time
    t.container.updateOverrides([
      repositoryProvider.overrideWithValue(t.repo),
      pairingConnectorProvider.overrideWithValue((label) async => t.device),
      pairingPollIntervalProvider.overrideWithValue(const Duration(milliseconds: 5)),
      pairingOnlineTimeoutProvider.overrideWithValue(const Duration(milliseconds: 200)),
    ]);
    await c.retry();
    expect(read(t.container).step, PairingStep.wifi);
  });

  test('Bluetooth problems map to their own failures', () async {
    for (final (reason, failure) in [
      ('off', PairingFailure.bluetoothOff),
      ('unauthorized', PairingFailure.bluetoothDenied),
      ('unsupported', PairingFailure.unsupported),
    ]) {
      final t = setup(connectError: BluetoothUnavailableException(reason));
      final c = ctl(t.container)..setLabel(label);
      await c.begin('Kitchen');
      expect(read(t.container).failure, failure, reason: reason);
    }
  });

  test('cancelling an unfinished pairing aborts the device and deletes the record', () async {
    final t = setup();
    final c = ctl(t.container)..setLabel(label);
    final before = (await t.repo.devices(h)).length;
    await c.begin('Kitchen');
    expect((await t.repo.devices(h)).length, before + 1);
    await c.cancel();
    expect(t.device.aborted, isTrue);
    expect(t.device.closed, isTrue);
    expect((await t.repo.devices(h)).length, before);
  });

  test('after a commit, leaving the wizard keeps the device', () async {
    final t = setup();
    final c = ctl(t.container)..setLabel(label);
    await c.begin('Kitchen');
    final id = read(t.container).deviceId!;
    await c.submitWifi('Home', 'x');
    await c.cancel();
    expect((await t.repo.devices(h)).any((d) => d.id == id), isTrue);
    expect(t.device.aborted, isFalse);
  });

  test('a lost connection during the test is a connection failure', () async {
    final device = _Dropping();
    final t = setup(device: device);
    final c = ctl(t.container)..setLabel(label);
    await c.begin('Kitchen');
    await c.submitWifi('Home', 'x');
    final s = read(t.container);
    expect(s.step, PairingStep.failed);
    expect(s.failure, PairingFailure.connection);
    expect(s.canRetry, isTrue);
  });
}

class _Dropping extends FakeDevice {
  @override
  Future<TestResult> test() async => throw TimeoutException('no answer from the device');
}
