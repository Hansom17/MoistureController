import 'download_io.dart' if (dart.library.js_interop) 'download_web.dart' as impl;

/// Hands a file to the user: a browser download on web. Returns false where that is not supported yet.
bool saveFile(String name, List<int> bytes, {String mime = 'application/octet-stream'}) =>
    impl.saveFile(name, bytes, mime);
