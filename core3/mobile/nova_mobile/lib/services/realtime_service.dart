import 'dart:async';

import 'package:supabase_flutter/supabase_flutter.dart';

import 'api_client.dart';

abstract class NovaRealtimeGateway {
  Future<void> start({
    required String accessToken,
    required String site,
    required Future<void> Function() onSignal,
  });

  Future<void> stop();

  void dispose();
}

class SupabaseNovaRealtimeGateway implements NovaRealtimeGateway {
  SupabaseNovaRealtimeGateway({required this.api});

  final NovaApiClient api;

  SupabaseClient? _client;
  RealtimeChannel? _channel;
  Timer? _signalDebounce;
  Future<void> Function()? _onSignal;
  String _accessToken = '';
  String _site = '';
  int _generation = 0;
  bool _disposed = false;

  @override
  Future<void> start({
    required String accessToken,
    required String site,
    required Future<void> Function() onSignal,
  }) async {
    if (_disposed) return;
    final token = accessToken.trim();
    final selectedSite = site.trim();
    if (token.isEmpty || selectedSite.isEmpty) {
      await stop();
      return;
    }

    final generation = ++_generation;
    await _disconnectCurrent();
    if (_disposed || generation != _generation) return;

    final config = await api.realtimeConfig(token);
    if (_disposed || generation != _generation) return;
    if (config.sessionSite.isNotEmpty && config.sessionSite != selectedSite) {
      throw const NovaApiException(
        status: 403,
        code: 'REALTIME_SITE_MISMATCH',
        message: 'Realtime 사업장 권한을 확인하세요.',
      );
    }

    final client = SupabaseClient(config.supabaseUrl, config.publishableKey);
    await client.realtime.setAuth(token);
    if (_disposed || generation != _generation) {
      await client.dispose();
      return;
    }

    _client = client;
    _accessToken = token;
    _site = selectedSite;
    _onSignal = onSignal;

    // Broadcast payload is intentionally ignored. It is only a wake-up signal;
    // Room State is always re-read from the authoritative Core API.
    final channel = client
        .channel(
          config.topicForSite(selectedSite),
          opts: const RealtimeChannelConfig(private: true),
        )
        .onBroadcast(event: 'UPDATE', callback: (_) => _scheduleSignal())
        .onBroadcast(event: 'INSERT', callback: (_) => _scheduleSignal());

    _channel = channel;
    // RealtimeClient owns heartbeat and exponential reconnect. The controller's
    // independent 15s authoritative reconcile remains the final recovery path.
    channel.subscribe();
  }

  Future<void> restart() async {
    final token = _accessToken;
    final site = _site;
    final callback = _onSignal;
    if (_disposed || token.isEmpty || site.isEmpty || callback == null) return;
    await start(accessToken: token, site: site, onSignal: callback);
  }

  void _scheduleSignal() {
    if (_disposed || _onSignal == null) return;
    _signalDebounce?.cancel();
    _signalDebounce = Timer(const Duration(milliseconds: 80), () {
      final callback = _onSignal;
      if (_disposed || callback == null) return;
      unawaited(Future<void>.sync(callback).catchError((_) {}));
    });
  }

  @override
  Future<void> stop() async {
    ++_generation;
    _accessToken = '';
    _site = '';
    _onSignal = null;
    await _disconnectCurrent();
  }

  Future<void> _disconnectCurrent() async {
    _signalDebounce?.cancel();
    _signalDebounce = null;
    final client = _client;
    final channel = _channel;
    _client = null;
    _channel = null;
    if (client == null) return;
    try {
      if (channel != null) await client.removeChannel(channel);
    } catch (_) {
      // dispose below is the stronger cleanup path.
    }
    try {
      await client.dispose();
    } catch (_) {}
  }

  @override
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    ++_generation;
    _signalDebounce?.cancel();
    _signalDebounce = null;
    _onSignal = null;
    _accessToken = '';
    _site = '';
    final client = _client;
    _client = null;
    _channel = null;
    if (client != null) unawaited(client.dispose());
  }
}
