import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/room.dart';
import '../models/session.dart';

class NovaApiException implements Exception {
  const NovaApiException({
    required this.status,
    required this.code,
    required this.message,
    this.retryable = false,
    this.reuseIdempotencyKey = false,
  });

  final int status;
  final String code;
  final String message;
  final bool retryable;
  final bool reuseIdempotencyKey;

  @override
  String toString() => 'NovaApiException($status, $code, $message)';
}

class NovaRealtimeConfig {
  const NovaRealtimeConfig({
    required this.supabaseUrl,
    required this.publishableKey,
    required this.privateChannel,
    required this.topicPattern,
    required this.sessionSite,
  });

  final String supabaseUrl;
  final String publishableKey;
  final bool privateChannel;
  final String topicPattern;
  final String sessionSite;

  factory NovaRealtimeConfig.fromJson(Map<String, dynamic> json) {
    final supabaseUrl = '${json['supabaseUrl'] ?? ''}'.trim();
    final publishableKey = '${json['publishableKey'] ?? ''}'.trim();
    final topicPattern = '${json['topicPattern'] ?? ''}'.trim();
    if (json['ok'] != true ||
        supabaseUrl.isEmpty ||
        publishableKey.isEmpty ||
        json['privateChannel'] != true ||
        topicPattern != 'nova:site:{site}:rooms') {
      throw const NovaApiException(
        status: 200,
        code: 'INVALID_REALTIME_CONFIG',
        message: 'Realtime 연결 설정을 확인할 수 없습니다.',
      );
    }
    return NovaRealtimeConfig(
      supabaseUrl: supabaseUrl,
      publishableKey: publishableKey,
      privateChannel: true,
      topicPattern: topicPattern,
      sessionSite: '${json['sessionSite'] ?? ''}'.trim(),
    );
  }

  String topicForSite(String site) => topicPattern.replaceFirst('{site}', site.trim());
}

class NovaRoomMutationResult {
  const NovaRoomMutationResult({
    required this.room,
    required this.requestId,
    required this.changed,
    required this.alreadyApplied,
  });

  final NovaRoom room;
  final String requestId;
  final bool changed;
  final bool alreadyApplied;
}

class NovaApiClient {
  NovaApiClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  final http.Client _http;
  final Random _random = Random.secure();

  Uri _uri(String path, [Map<String, String>? query]) {
    final base = Uri.parse(AppConfig.apiBaseUrl);
    return base.replace(
      path: path,
      queryParameters: query,
    );
  }

  Future<Map<String, dynamic>> _jsonRequest(
    String method,
    Uri uri, {
    String? accessToken,
    String? idempotencyKey,
    Map<String, dynamic>? body,
  }) async {
    final headers = <String, String>{
      'Accept': 'application/json',
      if (body != null) 'Content-Type': 'application/json',
      if (accessToken != null && accessToken.isNotEmpty)
        'Authorization': 'Bearer $accessToken',
      if (idempotencyKey != null && idempotencyKey.isNotEmpty)
        'Idempotency-Key': idempotencyKey,
      'X-NOVA-Client': 'flutter-alpha/0.1.0',
    };

    try {
      late http.Response response;
      if (method == 'GET') {
        response = await _http
            .get(uri, headers: headers)
            .timeout(AppConfig.requestTimeout);
      } else if (method == 'POST') {
        response = await _http
            .post(
              uri,
              headers: headers,
              body: jsonEncode(body ?? const <String, dynamic>{}),
            )
            .timeout(AppConfig.requestTimeout);
      } else {
        throw ArgumentError.value(method, 'method', 'unsupported method');
      }

      Map<String, dynamic> decoded;
      try {
        final raw = response.body.trim();
        decoded = raw.isEmpty
            ? <String, dynamic>{}
            : Map<String, dynamic>.from(jsonDecode(raw) as Map);
      } catch (_) {
        throw NovaApiException(
          status: response.statusCode,
          code: 'INVALID_SERVER_RESPONSE',
          message: '서버 응답을 확인할 수 없습니다.',
        );
      }

      if (response.statusCode >= 200 && response.statusCode < 300) {
        return decoded;
      }

      throw NovaApiException(
        status: response.statusCode,
        code: '${decoded['code'] ?? 'HTTP_ERROR'}'.trim(),
        message: '${decoded['message'] ?? '서버 요청에 실패했습니다.'}'.trim(),
        retryable: decoded['retryable'] == true,
        reuseIdempotencyKey: decoded['reuseIdempotencyKey'] == true,
      );
    } on TimeoutException {
      throw const NovaApiException(
        status: 0,
        code: 'NETWORK_TIMEOUT',
        message: '서버 응답이 지연되고 있습니다.',
        retryable: true,
        reuseIdempotencyKey: true,
      );
    } on NovaApiException {
      rethrow;
    } catch (_) {
      throw const NovaApiException(
        status: 0,
        code: 'NETWORK_ERROR',
        message: '네트워크 연결을 확인하세요.',
        retryable: true,
        reuseIdempotencyKey: true,
      );
    }
  }

  Future<NovaSession> login({
    required String name,
    required String employeeNo,
    required String site,
  }) async {
    final json = await _jsonRequest(
      'POST',
      _uri('/v1/session/login'),
      body: {
        'name': name.trim(),
        'employeeNo': employeeNo.trim(),
        'site': site.trim(),
      },
    );
    return NovaSession.fromLoginJson(json);
  }

  Future<NovaUser> me(String accessToken) async {
    final json = await _jsonRequest(
      'GET',
      _uri('/v1/session/me'),
      accessToken: accessToken,
    );
    return NovaUser.fromJson(json);
  }

  Future<NovaRealtimeConfig> realtimeConfig(String accessToken) async {
    final json = await _jsonRequest(
      'GET',
      _uri('/v1/realtime/config'),
      accessToken: accessToken,
    );
    return NovaRealtimeConfig.fromJson(json);
  }

  Future<List<NovaRoom>> listRooms({
    required String accessToken,
    required String businessDate,
    required String site,
  }) async {
    final json = await _jsonRequest(
      'GET',
      _uri('/v1/rooms', {
        'businessDate': businessDate,
        'site': site,
      }),
      accessToken: accessToken,
    );
    final rooms = json['rooms'] as List<dynamic>? ?? const [];
    return rooms
        .whereType<Map>()
        .map((item) => NovaRoom.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<NovaRoomMutationResult> mutateRoom({
    required String accessToken,
    required String businessDate,
    required String site,
    required String roomNo,
    required String action,
    required int expectedVersion,
    required String requestId,
  }) async {
    final json = await _jsonRequest(
      'POST',
      _uri('/v1/rooms/${Uri.encodeComponent(roomNo)}/actions'),
      accessToken: accessToken,
      idempotencyKey: requestId,
      body: {
        'businessDate': businessDate,
        'site': site,
        'action': action,
        'expectedVersion': expectedVersion,
      },
    );
    final roomJson = json['room'];
    if (roomJson is! Map) {
      throw const NovaApiException(
        status: 200,
        code: 'INVALID_ROOM_RESPONSE',
        message: '객실 처리 결과를 확인할 수 없습니다.',
      );
    }
    return NovaRoomMutationResult(
      room: NovaRoom.fromJson(Map<String, dynamic>.from(roomJson)),
      requestId: '${json['requestId'] ?? requestId}',
      changed: json['changed'] == true,
      alreadyApplied: json['alreadyApplied'] == true,
    );
  }

  String newRequestId(String roomNo, String action) {
    final micros = DateTime.now().toUtc().microsecondsSinceEpoch;
    final entropy = List<int>.generate(8, (_) => _random.nextInt(256))
        .map((value) => value.toRadixString(16).padLeft(2, '0'))
        .join();
    return 'NOVA-MOBILE-$action-$roomNo-$micros-$entropy';
  }

  void close() => _http.close();
}
