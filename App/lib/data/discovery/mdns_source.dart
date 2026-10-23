// mDNS needs dart:io; the web build has no multicast and finds nothing.
export 'mdns_source_stub.dart' if (dart.library.io) 'mdns_source_io.dart';
