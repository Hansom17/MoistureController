import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_reactive_ble/flutter_reactive_ble.dart';

import 'pairing_client.dart';
import 'pairing_session.dart';
import 'pairing_transport.dart';

/// The real Bluetooth: flutter_reactive_ble (BSD-3). Not exercised by the unit tests; the
/// session logic above it is. First try on a phone: see firmware/README.md "Pairing".
class ReactiveBlePairingTransportFactory implements PairingTransportFactory {
  ReactiveBlePairingTransportFactory([FlutterReactiveBle? ble]) : _ble = ble ?? FlutterReactiveBle();

  final FlutterReactiveBle _ble;

  @override
  Future<PairingTransport> connect(
    String bleName, {
    Duration findTimeout = const Duration(seconds: 30),
  }) async {
    await _requireReady();
    final id = await _find(bleName, findTimeout);

    final connected = Completer<void>();
    final sub = _ble
        .connectToDevice(id: id, connectionTimeout: const Duration(seconds: 20))
        .listen(
          (u) {
            if (u.connectionState == DeviceConnectionState.connected && !connected.isCompleted) {
              connected.complete();
            } else if (u.connectionState == DeviceConnectionState.disconnected &&
                !connected.isCompleted) {
              connected.completeError(StateError('could not connect'));
            }
          },
          onError: (Object e) {
            if (!connected.isCompleted) connected.completeError(e);
          },
        );
    try {
      await connected.future;
      final mtu = await _ble.requestMtu(deviceId: id, mtu: 247);
      final transport = _ReactiveBleTransport(_ble, id, sub, mtu);
      await transport._subscribe();
      return transport;
    } on Object {
      await sub.cancel();
      rethrow;
    }
  }

  Future<void> _requireReady() async {
    final status = await _ble.statusStream
        .firstWhere((s) => s != BleStatus.unknown)
        .timeout(const Duration(seconds: 5), onTimeout: () => BleStatus.unknown);
    switch (status) {
      case BleStatus.ready:
        return;
      case BleStatus.poweredOff:
        throw const BluetoothUnavailableException('off');
      case BleStatus.unauthorized:
        throw const BluetoothUnavailableException('unauthorized');
      case BleStatus.unsupported:
        throw const BluetoothUnavailableException('unsupported');
      default:
        throw const BluetoothUnavailableException('unavailable');
    }
  }

  Future<String> _find(String bleName, Duration timeout) async {
    final found = Completer<String>();
    final sub = _ble
        .scanForDevices(withServices: [Uuid.parse(serviceUuid)], scanMode: ScanMode.lowLatency)
        .listen((d) {
          if (d.name == bleName && !found.isCompleted) found.complete(d.id);
        }, onError: (Object e) {
          if (!found.isCompleted) found.completeError(e);
        });
    try {
      return await found.future.timeout(timeout, onTimeout: () => throw DeviceNotFoundException(bleName));
    } finally {
      await sub.cancel();
    }
  }
}

class _ReactiveBleTransport implements PairingTransport {
  _ReactiveBleTransport(this._ble, this._id, this._connection, this.mtu);

  final FlutterReactiveBle _ble;
  final String _id;
  final StreamSubscription<ConnectionStateUpdate> _connection;
  StreamSubscription<List<int>>? _notifications;
  final _queue = <Uint8List>[];
  Completer<void>? _waiter;
  Object? _lost;

  @override
  final int mtu;

  QualifiedCharacteristic _char(String uuid) => QualifiedCharacteristic(
    serviceId: Uuid.parse(serviceUuid),
    characteristicId: Uuid.parse(uuid),
    deviceId: _id,
  );

  Future<void> _subscribe() async {
    _connection.onData((u) {
      if (u.connectionState == DeviceConnectionState.disconnected) _fail(StateError('connection lost'));
    });
    _notifications = _ble.subscribeToCharacteristic(_char(txUuid)).listen(
      (data) {
        _queue.add(Uint8List.fromList(data));
        _waiter?.complete();
      },
      onError: _fail,
    );
    // the CCC descriptor is written when the subscription starts: give it a moment
    await Future<void>.delayed(const Duration(milliseconds: 300));
  }

  void _fail(Object e) {
    _lost = e;
    _waiter?.completeError(e);
  }

  @override
  Future<void> write(Uint8List data) =>
      _ble.writeCharacteristicWithResponse(_char(rxUuid), value: data);

  @override
  Future<Uint8List> read(Duration timeout) async {
    if (_queue.isEmpty) {
      if (_lost != null) throw _lost!;
      _waiter = Completer<void>();
      try {
        await _waiter!.future.timeout(timeout);
      } on TimeoutException {
        throw TimeoutException('no answer from the device');
      } finally {
        _waiter = null;
      }
    }
    return _queue.removeAt(0);
  }

  @override
  Future<void> close() async {
    await _notifications?.cancel();
    await _connection.cancel(); // dropping the subscription disconnects
  }
}
