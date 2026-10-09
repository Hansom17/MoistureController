import 'sse_io.dart' if (dart.library.js_interop) 'sse_web.dart' as impl;

/// One server-sent event.
class SseEvent {
  const SseEvent(this.event, this.data, {this.id});

  final String event;
  final String data;
  final String? id;
}

/// Opens an SSE stream; ends (done or error) when the connection drops.
///
/// Mobile/desktop: streamed HTTP response. Web: the browser's EventSource.
Stream<SseEvent> connectSse(Uri url, {String? lastEventId}) =>
    impl.connectSse(url, lastEventId: lastEventId);
