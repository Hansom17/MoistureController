import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

bool saveFile(String name, List<int> bytes, String mime) {
  final blob = web.Blob([Uint8List.fromList(bytes).toJS].toJS, web.BlobPropertyBag(type: mime));
  final url = web.URL.createObjectURL(blob);
  final a = web.HTMLAnchorElement()
    ..href = url
    ..download = name;
  a.click();
  web.URL.revokeObjectURL(url);
  return true;
}
