import 'dart:async';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

import 'sse.dart';

/// Event names the api sends (Gateway/specs.md 6.1 + hello and ping).
const _kinds = [
  'reading',
  'command',
  'device',
  'config',
  'plant',
  'rule',
  'alert',
  'installation',
  'join',
  'notification',
  'status',
  'resync',
  'hello',
];

Stream<SseEvent> connectSse(Uri url, {String? lastEventId}) {
  // EventSource can't send headers; the ticket in the URL authenticates.
  // Its own auto-reconnect would reuse the single-use ticket, so the first
  // error ends the stream and the repository reconnects with a new ticket.
  late final StreamController<SseEvent> controller;
  final source = web.EventSource(url.toString());
  controller = StreamController<SseEvent>(onCancel: () => source.close());
  for (final kind in _kinds) {
    source.addEventListener(
      kind,
      ((web.MessageEvent e) {
        controller.add(
          SseEvent(
            kind,
            (e.data as JSString?)?.toDart ?? '',
            id: e.lastEventId,
          ),
        );
      }).toJS,
    );
  }
  source.onerror = ((web.Event _) {
    source.close();
    controller.addError(StateError('SSE connection lost'));
    controller.close();
  }).toJS;
  return controller.stream;
}
