import 'dart:typed_data';

/// The device label `MCPOP1:<ble-name>:<pop>` (contracts/ble.md §7.6).
class PairingLabel {
  const PairingLabel(this.bleName, this.pop);

  /// What the device advertises, e.g. `MC-3F9A`.
  final String bleName;

  /// The 16 proof-of-possession bytes. A secret: never store or log it.
  final Uint8List pop;

  /// Null if [text] is not a MoistureController label.
  static PairingLabel? tryParse(String text) {
    final parts = text.trim().split(':');
    if (parts.length != 3 || parts[0] != 'MCPOP1') return null;
    final pop = decodePop(parts[2]);
    if (pop == null || parts[1].isEmpty) return null;
    return PairingLabel(parts[1], pop);
  }

  /// Builds a label from the name and the typed 26 characters (manual entry).
  static PairingLabel? fromManual(String bleName, String popText) {
    final pop = decodePop(popText);
    final name = bleName.trim().toUpperCase();
    if (pop == null || !RegExp(r'^MC-[0-9A-F]{4}$').hasMatch(name)) return null;
    return PairingLabel(name, pop);
  }
}

const _crockford = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

/// Crockford base32 of 16 bytes (26 characters); forgiving about case and the
/// look-alikes O/I/L. Null if it is not a PoP.
Uint8List? decodePop(String text, {int size = 16}) {
  final t = text
      .trim()
      .toUpperCase()
      .replaceAll('O', '0')
      .replaceAll('I', '1')
      .replaceAll('L', '1');
  final chars = (size * 8 + 4) ~/ 5;
  if (t.length != chars) return null;
  var n = BigInt.zero;
  for (final c in t.split('')) {
    final v = _crockford.indexOf(c);
    if (v < 0) return null;
    n = (n << 5) | BigInt.from(v);
  }
  n >>= chars * 5 - size * 8;
  final out = Uint8List(size);
  for (var i = size - 1; i >= 0; i--) {
    out[i] = (n & BigInt.from(0xff)).toInt();
    n >>= 8;
  }
  return out;
}

String encodePop(Uint8List pop) {
  var n = BigInt.zero;
  for (final b in pop) {
    n = (n << 8) | BigInt.from(b);
  }
  final bits = pop.length * 8;
  final chars = (bits + 4) ~/ 5;
  n <<= chars * 5 - bits;
  final out = StringBuffer();
  for (var i = chars - 1; i >= 0; i--) {
    out.write(_crockford[((n >> (5 * i)) & BigInt.from(31)).toInt()]);
  }
  return out.toString();
}
