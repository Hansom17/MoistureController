import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';

/// The app's side of the BLE session (contracts/ble.md §4, §7): handshake authenticated by the
/// PoP, then AES-128-GCM frames. Transport independent: bytes in, frames out. Checked against
/// `contracts/ble_vectors.json` (byte for byte) and the firmware's own implementation.
const pairingVersion = 1;
const maxMessage = 1024;
const maxBody = maxMessage + 16;
const serviceUuid = '6d630001-8a3f-4b6e-9d2c-7f1e5a9b0c01';
const rxUuid = '6d630002-8a3f-4b6e-9d2c-7f1e5a9b0c01'; // app -> device (write)
const txUuid = '6d630003-8a3f-4b6e-9d2c-7f1e5a9b0c01'; // device -> app (notify)

/// The session must end: bad frame or tag, wrong counter, a failed confirmation.
class SessionException implements Exception {
  const SessionException(this.code);

  /// `confirm_failed` = wrong device or wrong code; others are protocol errors.
  final String code;

  bool get wrongDeviceOrCode => code == 'confirm_failed';

  @override
  String toString() => 'SessionException($code)';
}

/// Frame bytes of one body: 2-byte big-endian length, then the body.
Uint8List frame(List<int> body) {
  if (body.length > maxBody) throw ArgumentError('frame body too large');
  return Uint8List.fromList([body.length >> 8, body.length & 0xff, ...body]);
}

/// Cuts [data] into ATT writes of at most `mtu - 3` bytes.
List<Uint8List> chunks(Uint8List data, int mtu) {
  final size = mtu > 4 ? mtu - 3 : 1;
  if (data.isEmpty) return [Uint8List(0)];
  return [
    for (var i = 0; i < data.length; i += size)
      Uint8List.sublistView(data, i, i + size > data.length ? data.length : i + size),
  ];
}

/// Turns the chunks of a stream back into frame bodies.
class FrameReader {
  var _data = Uint8List(0);

  List<Uint8List> feed(List<int> chunk) {
    _data = Uint8List.fromList([..._data, ...chunk]);
    final out = <Uint8List>[];
    while (_data.length >= 2) {
      final n = (_data[0] << 8) | _data[1];
      if (n > maxBody) throw const SessionException('frame_too_large');
      if (_data.length < 2 + n) break;
      out.add(Uint8List.sublistView(_data, 2, 2 + n));
      _data = Uint8List.sublistView(_data, 2 + n);
    }
    return out;
  }
}

/// What [PairingSession.feed] produced: frames to send back, decrypted messages.
class SessionOutput {
  const SessionOutput(this.frames, this.messages);

  final List<Uint8List> frames;
  final List<Map<String, dynamic>> messages;
}

class PairingSession {
  /// [seed] fixes the ephemeral private key (tests only); otherwise it is random.
  PairingSession({required Uint8List pop, Uint8List? seed})
    : _pop = Uint8List.fromList(pop),
      _seed = seed;

  final Uint8List _pop;
  final Uint8List? _seed;
  final _reader = FrameReader();
  final _x25519 = X25519();
  final _aes = AesGcm.with128bits();
  final _hmac = Hmac.sha256();

  SimpleKeyPair? _pair;
  Uint8List _a = Uint8List(0), _b = Uint8List(0), _nonceD = Uint8List(0);
  Uint8List _kEnc = Uint8List(0), _kMac = Uint8List(0);
  var _state = 'new'; // new -> hello_sent -> hello_acked -> open
  var _sendCounter = 0, _recvCounter = 0;

  bool get isOpen => _state == 'open';

  /// The first frame. Generates the ephemeral key pair.
  Future<Uint8List> hello() async {
    assert(_state == 'new');
    _pair = _seed != null
        ? await _x25519.newKeyPairFromSeed(_seed)
        : await _x25519.newKeyPair();
    _a = Uint8List.fromList((await _pair!.extractPublicKey()).bytes);
    _state = 'hello_sent';
    return frame(
      utf8.encode(jsonEncode({'t': 'hello', 'v': pairingVersion, 'pub': base64Encode(_a)})),
    );
  }

  Future<SessionOutput> feed(List<int> data) async {
    final frames = <Uint8List>[];
    final messages = <Map<String, dynamic>>[];
    for (final body in _reader.feed(data)) {
      if (_state == 'open') {
        messages.add(await _open(body));
      } else {
        frames.addAll(await _handshake(body));
      }
    }
    return SessionOutput(frames, messages);
  }

  /// Encrypts one message (after the handshake).
  Future<Uint8List> seal(Map<String, dynamic> message) async {
    assert(isOpen);
    final plain = utf8.encode(jsonEncode(message));
    if (plain.length > maxMessage) throw ArgumentError('message too large');
    final box = await _aes.encrypt(
      plain,
      secretKey: SecretKey(_kEnc),
      nonce: _nonce(0, _sendCounter),
    );
    _sendCounter++;
    return frame([...box.cipherText, ...box.mac.bytes]);
  }

  // --- handshake ---------------------------------------------------------------------------------

  Future<List<Uint8List>> _handshake(Uint8List body) async {
    final Map<String, dynamic> msg;
    try {
      msg = jsonDecode(utf8.decode(body)) as Map<String, dynamic>;
    } on Object {
      throw const SessionException('bad_handshake');
    }
    final kind = msg['t'];
    if (kind == 'error') {
      throw SessionException((msg['error'] as String?) ?? 'peer_error');
    }
    try {
      if (kind == 'hello_ack' && _state == 'hello_sent') {
        _b = base64Decode(msg['pub'] as String);
        _nonceD = base64Decode(msg['nonce'] as String);
        if (_b.length != 32 || _nonceD.length != 16) {
          throw const SessionException('bad_handshake');
        }
        await _deriveKeys();
        _state = 'hello_acked';
        final mac = await _confirm('app');
        return [
          frame(utf8.encode(jsonEncode({'t': 'confirm', 'mac': base64Encode(mac)}))),
        ];
      }
      if (kind == 'confirm' && _state == 'hello_acked') {
        final got = base64Decode(msg['mac'] as String);
        final want = await _confirm('dev');
        if (!_constantTimeEquals(got, want)) {
          throw const SessionException('confirm_failed'); // wrong device or wrong code
        }
        _state = 'open';
        return const [];
      }
    } on SessionException {
      rethrow;
    } on Object {
      throw const SessionException('bad_handshake');
    }
    throw const SessionException('bad_handshake');
  }

  Future<void> _deriveKeys() async {
    final shared = await _x25519.sharedSecretKey(
      keyPair: _pair!,
      remotePublicKey: SimplePublicKey(_b, type: KeyPairType.x25519),
    );
    final key = await Hkdf(hmac: _hmac, outputLength: 32).deriveKey(
      secretKey: shared,
      nonce: _pop, // HKDF salt
      info: [...utf8.encode('mc-ble-v1'), ..._a, ..._b, ..._nonceD],
    );
    final k = await key.extractBytes();
    _kEnc = Uint8List.fromList(k.sublist(0, 16));
    _kMac = Uint8List.fromList(k.sublist(16));
  }

  Future<Uint8List> _confirm(String who) async {
    final mac = await _hmac.calculateMac(
      [...utf8.encode(who), ..._a, ..._b, ..._nonceD],
      secretKey: SecretKey(_kMac),
    );
    return Uint8List.fromList(mac.bytes);
  }

  // --- encrypted frames ------------------------------------------------------------------------------

  Future<Map<String, dynamic>> _open(Uint8List body) async {
    if (body.length < 16) throw const SessionException('bad_frame');
    try {
      final box = SecretBox(
        body.sublist(0, body.length - 16),
        nonce: _nonce(1, _recvCounter),
        mac: Mac(body.sublist(body.length - 16)),
      );
      final plain = await _aes.decrypt(box, secretKey: SecretKey(_kEnc));
      final msg = jsonDecode(utf8.decode(plain)) as Map<String, dynamic>;
      _recvCounter++;
      return msg;
    } on Object {
      throw const SessionException('bad_frame');
    }
  }

  /// `direction` (0 app->device, 1 device->app), three zero bytes, 64-bit big-endian counter.
  static Uint8List _nonce(int direction, int counter) {
    final n = Uint8List(12);
    n[0] = direction;
    final d = ByteData.sublistView(n);
    d.setUint32(4, counter ~/ 0x100000000);
    d.setUint32(8, counter & 0xffffffff);
    return n;
  }

  static bool _constantTimeEquals(List<int> a, List<int> b) {
    if (a.length != b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) {
      diff |= a[i] ^ b[i];
    }
    return diff == 0;
  }
}
