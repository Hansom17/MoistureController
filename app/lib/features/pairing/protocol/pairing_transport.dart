import 'pairing_client.dart';

/// No device with that name was advertising in time.
class DeviceNotFoundException implements Exception {
  const DeviceNotFoundException(this.bleName);

  final String bleName;

  @override
  String toString() => 'DeviceNotFoundException($bleName)';
}

/// Bluetooth is off, not allowed or not available on this platform.
class BluetoothUnavailableException implements Exception {
  const BluetoothUnavailableException(this.reason);

  /// `off` · `unauthorized` · `unsupported` · `unavailable`
  final String reason;

  @override
  String toString() => 'BluetoothUnavailableException($reason)';
}

/// Finds a device by its advertised name and opens a [PairingTransport] to it.
abstract class PairingTransportFactory {
  /// Throws [DeviceNotFoundException] after [findTimeout], [BluetoothUnavailableException]
  /// if Bluetooth can't be used, or any connection error.
  Future<PairingTransport> connect(
    String bleName, {
    Duration findTimeout = const Duration(seconds: 30),
  });
}

/// Web and desktop builds: no pairing (App_Specs §11: mobile only).
class UnsupportedPairingTransportFactory implements PairingTransportFactory {
  const UnsupportedPairingTransportFactory();

  @override
  Future<PairingTransport> connect(String bleName, {Duration findTimeout = const Duration(seconds: 30)}) =>
      throw const BluetoothUnavailableException('unsupported');
}
