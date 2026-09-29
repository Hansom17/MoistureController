import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import 'sse.dart';

Stream<SseEvent> connectSse(Uri url, {String? lastEventId}) async* {
  final dio = Dio();
  final response = await dio.getUri<ResponseBody>(
    url,
    options: Options(
      responseType: ResponseType.stream,
      headers: {'Accept': 'text/event-stream', 'Last-Event-ID': ?lastEventId},
    ),
  );
  String? id;
  var event = 'message';
  final data = StringBuffer();
  final lines = response.data!.stream
      .cast<List<int>>()
      .transform(utf8.decoder)
      .transform(const LineSplitter());
  await for (final line in lines) {
    if (line.isEmpty) {
      if (data.isNotEmpty) {
        yield SseEvent(event, data.toString().trimRight(), id: id);
      }
      event = 'message';
      data.clear();
    } else if (line.startsWith('id:')) {
      id = line.substring(3).trim();
    } else if (line.startsWith('event:')) {
      event = line.substring(6).trim();
    } else if (line.startsWith('data:')) {
      data.writeln(line.substring(5).trimLeft());
    }
  }
}
