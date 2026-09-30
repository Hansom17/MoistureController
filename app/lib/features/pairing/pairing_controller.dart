import 'dart:async';
import 'package:flutter/foundation.dart' show TargetPlatform, defaultTargetPlatform, kIsWeb;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/session.dart';
import '../../data/api_problem.dart';
import '../../data/models.dart';
import '../../data/repositories/moisture_repository.dart';
import 'protocol/pairing_client.dart';
import 'protocol/pairing_label.dart';
import 'protocol/pairing_session.dart';
import 'protocol/pairing_transport.dart';
import 'protocol/reactive_ble_transport.dart';

/// Real Bluetooth on Android and iOS, nothing elsewhere (App_Specs §11). Tests override this.
final pairingTransportFactoryProvider = Provider<PairingTransportFactory>(
  (ref) => !kIsWeb &&
          (defaultTargetPlatform == TargetPlatform.android ||
              defaultTargetPlatform == TargetPlatform.iOS)
      ? ReactiveBlePairingTransportFactory()
      : const UnsupportedPairingTransportFactory(),
);

/// Opens the encrypted channel to the device named on the label. Tests replace this with a fake
/// device; the real one finds it over Bluetooth and returns the PoP-authenticated client.
typedef PairingConnector = Future<PairingDevice> Function(PairingLabel label);

final pairingConnectorProvider = Provider<PairingConnector>((ref) {
  final factory = ref.watch(pairingTransportFactoryProvider);
  return (label) async {
    final transport = await factory.connect(label.bleName);
    return PairingClient(transport, label.pop);
  };
});

/// How often the wizard looks whether the device came online. Tests make it short.
final pairingPollIntervalProvider = Provider<Duration>((ref) => const Duration(seconds: 3));
final pairingOnlineTimeoutProvider = Provider<Duration>((ref) => const Duration(seconds: 90));

enum PairingStep { label, name, working, wifi, testing, finishing, done, failed }

/// What the `working` step is doing right now.
enum PairingWork { creating, finding, handshake, scanning }

enum PairingFailure {
  noGateway,
  gatewayOffline,
  notFound,
  wrongCode,
  connection,
  bluetoothOff,
  bluetoothDenied,
  unsupported,
  other,
}

class PairingState {
  const PairingState({
    this.step = PairingStep.label,
    this.work = PairingWork.creating,
    this.label,
    this.name = '',
    this.networks = const [],
    this.failure,
    this.detail = '',
    this.testError,
    this.deviceId,
    this.stillWaiting = false,
  });

  final PairingStep step;
  final PairingWork work;
  final PairingLabel? label;
  final String name;
  final List<WifiNetwork> networks;
  final PairingFailure? failure;
  final String detail;

  /// The last `test` result that was not ok (the wizard returns to the WiFi step).
  final TestResult? testError;
  final String? deviceId;

  /// Done, but the device did not show up online within the wait (it may just be slow).
  final bool stillWaiting;

  /// A failure after which starting over from the connection makes sense (record is kept).
  bool get canRetry =>
      failure == PairingFailure.notFound ||
      failure == PairingFailure.connection ||
      failure == PairingFailure.bluetoothOff ||
      failure == PairingFailure.bluetoothDenied;

  PairingState copyWith({
    PairingStep? step,
    PairingWork? work,
    PairingLabel? label,
    String? name,
    List<WifiNetwork>? networks,
    PairingFailure? failure,
    String? detail,
    TestResult? testError,
    bool clearTestError = false,
    String? deviceId,
    bool? stillWaiting,
  }) => PairingState(
    step: step ?? this.step,
    work: work ?? this.work,
    label: label ?? this.label,
    name: name ?? this.name,
    networks: networks ?? this.networks,
    failure: step == null || step != PairingStep.failed ? null : (failure ?? this.failure),
    detail: detail ?? this.detail,
    testError: clearTestError ? null : (testError ?? this.testError),
    deviceId: deviceId ?? this.deviceId,
    stillWaiting: stillWaiting ?? this.stillWaiting,
  );
}

final pairingControllerProvider = NotifierProvider.autoDispose
    .family<PairingController, PairingState, String>(PairingController.new);

/// The add-device flow of contracts/ble.md §6. The pairing bundle (device key) and the PoP live
/// only in this object's memory; nothing is stored or logged.
class PairingController extends Notifier<PairingState> {
  PairingController(this.householdId);

  final String householdId;

  /// Kept from build(): the cleanup runs while the provider is being disposed.
  late MoistureRepository _repo;
  PairingBundle? _bundle;
  PairingDevice? _client;
  var _committed = false;
  var _disposed = false;

  @override
  PairingState build() {
    _repo = ref.read(repositoryProvider);
    ref.onDispose(() {
      _disposed = true;
      unawaited(_cleanUp());
    });
    return const PairingState();
  }

  void setLabel(PairingLabel label) =>
      state = state.copyWith(step: PairingStep.name, label: label);

  /// Back to the label step (scanned the wrong thing).
  void reset() => state = const PairingState();

  /// Creates the device record, then connects. The gateway must be online (checked by the API).
  Future<void> begin(String name) async {
    state = state.copyWith(step: PairingStep.working, work: PairingWork.creating, name: name);
    try {
      final created = await _repo.createDevice(householdId, name.trim());
      _bundle = created.bundle;
      state = state.copyWith(deviceId: created.device.id);
    } on ApiProblem catch (e) {
      _fail(switch (e.type) {
        ApiProblem.noGateway => PairingFailure.noGateway,
        ApiProblem.gatewayOffline => PairingFailure.gatewayOffline,
        _ => PairingFailure.other,
      }, e.detail ?? '');
      return;
    } on Object catch (e) {
      _fail(PairingFailure.other, '$e');
      return;
    }
    await _connect();
  }

  /// After `notFound` / `connection`: the device record exists already.
  Future<void> retry() => _connect();

  Future<void> _connect() async {
    final label = state.label!;
    await _closeClient();
    try {
      state = state.copyWith(step: PairingStep.working, work: PairingWork.finding);
      final client = await ref.read(pairingConnectorProvider)(label);
      if (_disposed) {
        await client.close();
        return;
      }
      _client = client;

      state = state.copyWith(work: PairingWork.handshake);
      await client.open();
      await client.info(); // proves the encrypted channel works in both directions

      state = state.copyWith(work: PairingWork.scanning);
      var networks = <WifiNetwork>[];
      try {
        networks = await client.wifiScan(); // a convenience: typing the name works too
      } on Object {
        // ignored on purpose
      }
      if (_disposed) return;
      state = state.copyWith(step: PairingStep.wifi, networks: networks, clearTestError: true);
    } on DeviceNotFoundException {
      _fail(PairingFailure.notFound);
    } on BluetoothUnavailableException catch (e) {
      _fail(switch (e.reason) {
        'off' => PairingFailure.bluetoothOff,
        'unauthorized' => PairingFailure.bluetoothDenied,
        'unsupported' => PairingFailure.unsupported,
        _ => PairingFailure.connection,
      });
    } on SessionException catch (e) {
      if (e.wrongDeviceOrCode) {
        await _deleteRecord(); // nothing was configured: take the record back
        _fail(PairingFailure.wrongCode);
      } else {
        _fail(PairingFailure.connection, e.code);
      }
    } on Object catch (e) {
      _fail(PairingFailure.connection, '$e');
    }
  }

  /// WiFi settings + gateway bundle to the device, test, and on success commit.
  Future<void> submitWifi(String ssid, String password) async {
    final client = _client;
    final bundle = _bundle;
    if (client == null || bundle == null) return;
    state = state.copyWith(step: PairingStep.testing, clearTestError: true);
    try {
      await client.setWifi(ssid, password);
      await client.setMqtt(
        deviceId: bundle.deviceId,
        host: bundle.host,
        port: bundle.port,
        psk: bundle.psk,
      );
      final result = await client.test();
      if (_disposed) return;
      if (!result.ok) {
        // back to the WiFi step with the reason; the connection stays open
        state = state.copyWith(step: PairingStep.wifi, testError: result);
        return;
      }
      state = state.copyWith(step: PairingStep.finishing);
      await client.commit();
      _committed = true;
      await _closeClient();
      await _waitOnline();
    } on DeviceRequestException catch (e) {
      state = state.copyWith(
        step: PairingStep.wifi,
        testError: TestResult(wifiOk: false, mqttOk: false, detail: e.detail.isEmpty ? e.code : e.detail),
      );
    } on Object catch (e) {
      _fail(PairingFailure.connection, '$e');
    }
  }

  Future<void> _waitOnline() async {
    final interval = ref.read(pairingPollIntervalProvider);
    // counted, not timed: the same in real time and in fake-time tests
    final polls = (ref.read(pairingOnlineTimeoutProvider).inMicroseconds /
            interval.inMicroseconds)
        .ceil();
    final id = _bundle!.deviceId;
    for (var i = 0; i < polls && !_disposed; i++) {
      try {
        final devices = await _repo.devices(householdId);
        final d = devices.where((d) => d.id == id).firstOrNull;
        if (d != null && d.state != DeviceState.offline) {
          state = state.copyWith(step: PairingStep.done, stillWaiting: false);
          return;
        }
      } on Object {
        // keep waiting: the connection may just be slow
      }
      await Future<void>.delayed(interval);
    }
    if (!_disposed) state = state.copyWith(step: PairingStep.done, stillWaiting: true);
  }

  /// The user leaves the wizard. An unfinished pairing takes its device record back.
  Future<void> cancel() async {
    await _cleanUp();
  }

  // --- helpers -------------------------------------------------------------------------------------

  void _fail(PairingFailure failure, [String detail = '']) =>
      state = state.copyWith(step: PairingStep.failed, failure: failure, detail: detail);

  Future<void> _closeClient() async {
    final c = _client;
    _client = null;
    try {
      await c?.close();
    } on Object {
      // already gone
    }
  }

  Future<void> _deleteRecord() async {
    final id = _bundle?.deviceId;
    _bundle = null;
    if (id == null) return;
    try {
      await _repo.deleteDevice(householdId, id);
    } on Object {
      // best effort: an orphan record can be deleted in the app
    }
  }

  Future<void> _cleanUp() async {
    final c = _client;
    if (c != null && !_committed) {
      try {
        await c.abort(); // the device forgets what it was given
      } on Object {
        // not reachable any more
      }
    }
    await _closeClient();
    if (!_committed) await _deleteRecord();
  }
}
