import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:moisture_controller/features/pairing/protocol/pairing_client.dart';
import 'package:moisture_controller/features/pairing/protocol/pairing_label.dart';
import 'package:moisture_controller/features/pairing/protocol/pairing_session.dart';

/// The vectors the firmware and the Python reference are checked against.
Map<String, dynamic> loadVectors() =>
    jsonDecode(File('../contracts/ble_vectors.json').readAsStringSync())
        as Map<String, dynamic>;

Uint8List hex(String s) => Uint8List.fromList([
  for (var i = 0; i < s.length; i += 2) int.parse(s.substring(i, i + 2), radix: 16),
]);

String toHex(List<int> b) => b.map((x) => x.toRadixString(16).padLeft(2, '0')).join();

/// Replays a scripted session: our frames must equal the vector's app frames byte for byte,
/// fed only with the device frames from the vector.
Future<PairingSession> replay(Map<String, dynamic> v, String framesKey) async {
  final frames = (v[framesKey] as List).cast<Map<String, dynamic>>();
  final s = PairingSession(pop: hex(v['pop'] as String), seed: hex(v['app_private'] as String));
  final sent = <String>[];
  sent.add(toHex(await s.hello()));
  // only the handshake: hello_ack (frame 1) and the device's confirm (frame 3)
  for (final i in [1, 3]) {
    final out = await s.feed(hex(frames[i]['frame'] as String));
    sent.addAll(out.frames.map(toHex));
  }
  // the app frames of the vector that are replies to the handshake
  final expected = frames.where((f) => f['dir'] == 'app->dev').map((f) => f['frame']).toList();
  expect(sent, expected.take(2).toList(), reason: 'handshake frames');
  return s;
}

void main() {
  final v = loadVectors();

  group('vectors', () {
    test('handshake and keys match the reference byte for byte', () async {
      final s = await replay(v, 'frames');
      expect(s.isOpen, isTrue);
    });

    test('encrypted requests equal the reference frames and replies decrypt', () async {
      final frames = (v['frames'] as List).cast<Map<String, dynamic>>();
      final requests = (v['requests'] as List).cast<Map<String, dynamic>>();
      final responses = (v['responses'] as List).cast<Map<String, dynamic>>();
      final s = await replay(v, 'frames');
      var ri = 0;
      for (var i = 4; i < frames.length; i += 2) {
        final sealed = await s.seal(requests[ri]);
        expect(toHex(sealed), frames[i]['frame'], reason: 'request ${ri + 1}');
        final out = await s.feed(hex(frames[i + 1]['frame'] as String));
        expect(out.messages, [responses[ri]], reason: 'reply ${ri + 1}');
        ri++;
      }
    });

    test('the second session (operations and errors) also matches', () async {
      final frames = (v['ops_frames'] as List).cast<Map<String, dynamic>>();
      final requests = (v['ops_requests'] as List).cast<Map<String, dynamic>>();
      final responses = (v['ops_responses'] as List).cast<Map<String, dynamic>>();
      final s = await replay(v, 'ops_frames');
      for (var i = 4, r = 0; i < frames.length; i += 2, r++) {
        expect(toHex(await s.seal(requests[r])), frames[i]['frame']);
        expect((await s.feed(hex(frames[i + 1]['frame'] as String))).messages, [responses[r]]);
      }
    });

    test('a wrong PoP fails the confirmation with "wrong device or code"', () async {
      final frames = (v['frames'] as List).cast<Map<String, dynamic>>();
      final s = PairingSession(pop: Uint8List(16), seed: hex(v['app_private'] as String));
      await s.hello();
      await s.feed(hex(frames[1]['frame'] as String)); // hello_ack: keys differ now
      expect(
        () => s.feed(hex(frames[3]['frame'] as String)), // the genuine device's confirm
        throwsA(isA<SessionException>().having((e) => e.wrongDeviceOrCode, 'wrong code', true)),
      );
    });

    test('tampered, replayed and reflected frames end the session', () async {
      final frames = (v['frames'] as List).cast<Map<String, dynamic>>();
      Future<PairingSession> open() => replay(v, 'frames');
      var s = await open();
      final bad = hex(frames[5]['frame'] as String)..[20] ^= 1;
      await expectLater(s.feed(bad), throwsA(isA<SessionException>()));
      s = await open();
      await s.feed(hex(frames[5]['frame'] as String));
      await expectLater(
        s.feed(hex(frames[5]['frame'] as String)), // replay of the first reply
        throwsA(isA<SessionException>()),
      );
      s = await open();
      await expectLater(
        s.feed(hex(frames[4]['frame'] as String)), // the app's own request reflected back
        throwsA(isA<SessionException>()),
      );
    });
  });

  group('framing', () {
    test('frames survive any fragmentation', () async {
      final frames = (v['frames'] as List).cast<Map<String, dynamic>>();
      final whole = hex(frames[1]['frame'] as String);
      for (final mtu in [23, 24, 50, 185, 247]) {
        final reader = FrameReader();
        final bodies = [for (final c in chunks(whole, mtu)) ...reader.feed(c)];
        expect(bodies.length, 1, reason: 'mtu $mtu');
        expect(toHex(frame(bodies.single)), toHex(whole));
      }
      final reader = FrameReader();
      final bodies = [for (final b in whole) ...reader.feed([b])];
      expect(bodies.length, 1);
    });

    test('an oversized length ends the session', () {
      expect(() => FrameReader().feed([0xff, 0xff]), throwsA(isA<SessionException>()));
    });
  });

  group('label', () {
    test('parses the vector label and round-trips', () {
      final label = PairingLabel.tryParse(v['label'] as String)!;
      expect(label.bleName, 'MC-3F9A');
      expect(toHex(label.pop), v['pop']);
      expect(encodePop(label.pop), (v['label'] as String).split(':')[2]);
    });

    test('is forgiving about case and look-alikes, strict about the rest', () {
      final pop = encodePop(hex(v['pop'] as String));
      expect(decodePop(pop.toLowerCase().replaceAll('0', 'O')), hex(v['pop'] as String));
      expect(PairingLabel.tryParse('MCPOP2:MC-3F9A:$pop'), isNull);
      expect(PairingLabel.tryParse('MCPOP1:MC-3F9A'), isNull);
      expect(PairingLabel.tryParse('hello'), isNull);
      expect(PairingLabel.tryParse('MCPOP1:MC-3F9A:${pop.substring(1)}'), isNull);
      expect(PairingLabel.fromManual('mc-26ea', pop)!.bleName, 'MC-26EA');
      expect(PairingLabel.fromManual('26EA', pop), isNull);
    });
  });

  group('client flow against a loopback device', () {
    test('handshake, info and operations over a small MTU', () async {
      final frames = (v['frames'] as List).cast<Map<String, dynamic>>();
      final t = ScriptedDevice(v, 'frames', mtu: 23);
      final client = PairingClient(t, hex(v['pop'] as String), seed: hex(v['app_private'] as String));
      await client.open();
      final info = await client.info();
      expect(info.hwMac, '24:6F:28:AA:BB:CC');
      expect(info.provisioned, isFalse);
      await client.setWifi('Home "5G"', 'pa\\ss wörd');
      await client.setMqtt(
        deviceId: 'mc-8f3kq2v7xw1m9hzt',
        host: '192.168.1.20',
        port: 8883,
        psk: 'ab' * 32,
      );
      await expectLater(
        client.request('fly'),
        throwsA(isA<DeviceRequestException>().having((e) => e.code, 'code', 'unknown_op')),
      );
      await client.commit();
      expect(t.served, frames.length ~/ 2);
    });
  });
}

/// A device that answers with the vector's frames: each app write completes a frame, which is
/// checked against the expected app frame and answered with the recorded device frame.
class ScriptedDevice implements PairingTransport {
  ScriptedDevice(Map<String, dynamic> v, String key, {required this.mtu})
    : _frames = (v[key] as List).cast<Map<String, dynamic>>();

  final List<Map<String, dynamic>> _frames;
  @override
  final int mtu;
  final _queue = <Uint8List>[];
  final _received = <int>[];
  var _next = 0;
  var served = 0;

  @override
  Future<void> write(Uint8List data) async {
    expect(data.length, lessThanOrEqualTo(mtu - 3), reason: 'ATT write too large');
    _received.addAll(data);
    while (_received.length >= 2) {
      final n = (_received[0] << 8) | _received[1];
      if (_received.length < 2 + n) return;
      final got = toHex(_received.sublist(0, 2 + n));
      _received.removeRange(0, 2 + n);
      expect(got, _frames[_next]['frame'], reason: 'app frame #$_next');
      _next++;
      served++;
      final reply = hex(_frames[_next]['frame'] as String);
      _next++;
      _queue.addAll(chunks(reply, mtu));
    }
  }

  @override
  Future<Uint8List> read(Duration timeout) async {
    if (_queue.isEmpty) throw TimeoutException('no notification');
    return _queue.removeAt(0);
  }

  @override
  Future<void> close() async {}
}
