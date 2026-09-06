import 'package:flutter/foundation.dart';

import '../config/app_config.dart';
import '../models/room.dart';
import '../models/session.dart';
import '../services/api_client.dart';
import '../services/session_store.dart';

class AppController extends ChangeNotifier {
  AppController({NovaApiClient? apiClient, SessionStore? sessionStore})
      : api = apiClient ?? NovaApiClient(),
        store = sessionStore ?? SessionStore();

  final NovaApiClient api;
  final SessionStore store;

  NovaSession? session;
  List<NovaRoom> rooms = const [];
  bool bootstrapping = true;
  bool signingIn = false;
  bool loadingRooms = false;
  String? globalError;
  final Set<String> pendingRoomNos = <String>{};

  bool get isAuthenticated => session != null;
  NovaUser? get user => session?.user;
  String get businessDate => AppConfig.businessDate();

  Future<void> bootstrap() async {
    bootstrapping = true;
    globalError = null;
    notifyListeners();
    try {
      final saved = await store.read();
      if (saved == null || saved.accessToken.isEmpty) {
        session = null;
        rooms = const [];
        return;
      }
      final verifiedUser = await api.me(saved.accessToken);
      session = saved.withVerifiedUser(verifiedUser);
      await store.save(session!);
      if (verifiedUser.role == 'ROOMMAID' && verifiedUser.sessionSite.isNotEmpty) {
        await refreshRooms(silent: true);
      }
    } on NovaApiException catch (error) {
      if (error.status == 401 || error.status == 403) {
        await store.clear();
        session = null;
        rooms = const [];
      } else {
        globalError = error.message;
      }
    } finally {
      bootstrapping = false;
      notifyListeners();
    }
  }

  Future<bool> login({required String name, required String employeeNo, required String site}) async {
    signingIn = true;
    globalError = null;
    notifyListeners();
    try {
      final next = await api.login(name: name, employeeNo: employeeNo, site: site);
      if (next.user.role != 'ROOMMAID') {
        globalError = '현재 모바일 알파는 룸메이드 계정만 지원합니다.';
        return false;
      }
      session = next;
      await store.save(next);
      await refreshRooms(silent: true);
      return true;
    } on NovaApiException catch (error) {
      globalError = error.message;
      return false;
    } finally {
      signingIn = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    await store.clear();
    session = null;
    rooms = const [];
    pendingRoomNos.clear();
    globalError = null;
    notifyListeners();
  }

  Future<void> refreshRooms({bool silent = false}) async {
    final active = session;
    if (active == null || active.user.sessionSite.isEmpty) return;
    if (!silent) {
      loadingRooms = true;
      globalError = null;
      notifyListeners();
    }
    try {
      rooms = await api.listRooms(
        accessToken: active.accessToken,
        businessDate: businessDate,
        site: active.user.sessionSite,
      );
      globalError = null;
    } on NovaApiException catch (error) {
      if (error.status == 401) {
        await logout();
      } else if (!silent) {
        globalError = error.message;
      }
    } finally {
      if (!silent) loadingRooms = false;
      notifyListeners();
    }
  }

  Future<bool> performAction(NovaRoom room, String action) async {
    final active = session;
    if (active == null || pendingRoomNos.contains(room.roomNo)) return false;

    final requestId = api.newRequestId(room.roomNo, action);
    final original = room;
    final optimisticStatus = action == 'CLEANING_START'
        ? 'CLEANING'
        : (room.qmEmployeeNo.isNotEmpty ? 'QM_WAITING' : 'COMPLETED');

    pendingRoomNos.add(room.roomNo);
    _replaceRoom(room.copyWith(cleaningStatus: optimisticStatus));
    globalError = null;
    notifyListeners();

    try {
      final result = await api.mutateRoom(
        accessToken: active.accessToken,
        businessDate: room.businessDate,
        site: room.site,
        roomNo: room.roomNo,
        action: action,
        expectedVersion: room.version,
        requestId: requestId,
      );
      _replaceRoom(result.room);
      return true;
    } on NovaApiException catch (error) {
      if (await _reconcileRoom(room.roomNo, action)) return true;

      if (error.retryable && error.reuseIdempotencyKey) {
        try {
          final result = await api.mutateRoom(
            accessToken: active.accessToken,
            businessDate: room.businessDate,
            site: room.site,
            roomNo: room.roomNo,
            action: action,
            expectedVersion: room.version,
            requestId: requestId,
          );
          _replaceRoom(result.room);
          return true;
        } on NovaApiException catch (retryError) {
          if (await _reconcileRoom(room.roomNo, action)) return true;
          globalError = retryError.message;
        }
      } else {
        globalError = error.message;
      }
      _replaceRoom(original);
      return false;
    } finally {
      pendingRoomNos.remove(room.roomNo);
      notifyListeners();
    }
  }

  Future<bool> _reconcileRoom(String roomNo, String action) async {
    final active = session;
    if (active == null) return false;
    try {
      final latest = await api.listRooms(
        accessToken: active.accessToken,
        businessDate: businessDate,
        site: active.user.sessionSite,
      );
      rooms = latest;
      NovaRoom? matched;
      for (final item in latest) {
        if (item.roomNo == roomNo) {
          matched = item;
          break;
        }
      }
      return matched?.isDesiredFor(action) ?? false;
    } catch (_) {
      return false;
    }
  }

  void _replaceRoom(NovaRoom updated) {
    final next = [...rooms];
    final index = next.indexWhere((item) => item.roomNo == updated.roomNo);
    if (index >= 0) {
      next[index] = updated;
    } else {
      next.add(updated);
    }
    rooms = next;
  }

  @override
  void dispose() {
    api.close();
    super.dispose();
  }
}
