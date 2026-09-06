import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:nova_mobile/models/room.dart';
import 'package:nova_mobile/models/session.dart';
import 'package:nova_mobile/services/api_client.dart';
import 'package:nova_mobile/services/realtime_service.dart';
import 'package:nova_mobile/services/session_store.dart';
import 'package:nova_mobile/state/app_controller.dart';

void main() {
  test('login starts site-scoped Realtime and signal triggers authoritative room read', () async {
    final initialRoom = _room(cleaningStatus: 'WAITING', version: 1);
    final updatedRoom = _room(cleaningStatus: 'CLEANING', version: 2);
    final api = _FakeApiClient(
      loginSession: _roommaidSession(),
      roomSnapshots: [
        [initialRoom],
        [updatedRoom],
      ],
    );
    final realtime = _FakeRealtimeGateway();
    final controller = AppController(
      apiClient: api,
      sessionStore: _FakeSessionStore(),
      realtimeGateway: realtime,
    );
    addTearDown(controller.dispose);

    expect(
      await controller.login(name: '테스트', employeeNo: '10001', site: '쏘라노'),
      isTrue,
    );
    expect(realtime.starts, 1);
    expect(realtime.accessToken, 'test-access-token');
    expect(realtime.site, '쏘라노');
    expect(controller.rooms.single.cleaningStatus, 'WAITING');

    await realtime.emitSignal();

    expect(api.listRoomsCalls, 2);
    expect(controller.rooms.single.cleaningStatus, 'CLEANING');
    expect(controller.rooms.single.version, 2);
  });

  test('Realtime signal cannot overwrite an in-flight optimistic room action', () async {
    final initialRoom = _room(cleaningStatus: 'WAITING', version: 1);
    final staleRoom = _room(cleaningStatus: 'WAITING', version: 1);
    final committedRoom = _room(cleaningStatus: 'CLEANING', version: 2);
    final mutation = Completer<NovaRoomMutationResult>();
    final api = _FakeApiClient(
      loginSession: _roommaidSession(),
      roomSnapshots: [
        [initialRoom],
        [staleRoom],
      ],
      mutation: mutation,
    );
    final realtime = _FakeRealtimeGateway();
    final controller = AppController(
      apiClient: api,
      sessionStore: _FakeSessionStore(),
      realtimeGateway: realtime,
    );
    addTearDown(controller.dispose);

    expect(
      await controller.login(name: '테스트', employeeNo: '10001', site: '쏘라노'),
      isTrue,
    );
    expect(controller.rooms.single.cleaningStatus, 'WAITING');

    final actionFuture = controller.performAction(initialRoom, 'CLEANING_START');
    await Future<void>.delayed(Duration.zero);

    expect(controller.pendingRoomNos, contains('6514'));
    expect(controller.rooms.single.cleaningStatus, 'CLEANING');

    // The Broadcast body itself is ignored. Its signal causes a stale
    // authoritative GET here, which still must not roll back optimistic state.
    await realtime.emitSignal();

    expect(controller.pendingRoomNos, contains('6514'));
    expect(controller.rooms.single.cleaningStatus, 'CLEANING');
    expect(controller.rooms.single.version, 1);

    mutation.complete(
      NovaRoomMutationResult(
        room: committedRoom,
        requestId: 'NOVA-MOBILE-TEST-START-6514',
        changed: true,
        alreadyApplied: false,
      ),
    );

    expect(await actionFuture, isTrue);
    expect(controller.pendingRoomNos, isNot(contains('6514')));
    expect(controller.rooms.single.cleaningStatus, 'CLEANING');
    expect(controller.rooms.single.version, 2);
    expect(api.listRoomsCalls, 2);
  });

  test('logout stops Realtime before clearing the session', () async {
    final api = _FakeApiClient(
      loginSession: _roommaidSession(),
      roomSnapshots: [
        [_room(cleaningStatus: 'WAITING', version: 1)],
      ],
    );
    final store = _FakeSessionStore();
    final realtime = _FakeRealtimeGateway();
    final controller = AppController(
      apiClient: api,
      sessionStore: store,
      realtimeGateway: realtime,
    );
    addTearDown(controller.dispose);

    expect(
      await controller.login(name: '테스트', employeeNo: '10001', site: '쏘라노'),
      isTrue,
    );
    await controller.logout();

    expect(realtime.stops, 1);
    expect(controller.isAuthenticated, isFalse);
    expect(controller.rooms, isEmpty);
    expect(store.clearCalls, 1);
  });

  test('app resume performs immediate authoritative read and restarts Realtime', () async {
    final api = _FakeApiClient(
      loginSession: _roommaidSession(),
      roomSnapshots: [
        [_room(cleaningStatus: 'WAITING', version: 1)],
        [_room(cleaningStatus: 'CLEANING', version: 2)],
      ],
    );
    final realtime = _FakeRealtimeGateway();
    final controller = AppController(
      apiClient: api,
      sessionStore: _FakeSessionStore(),
      realtimeGateway: realtime,
    );
    addTearDown(controller.dispose);

    await controller.login(name: '테스트', employeeNo: '10001', site: '쏘라노');
    await controller.handleAppResumed();

    expect(api.listRoomsCalls, 2);
    expect(realtime.starts, 2);
    expect(controller.rooms.single.cleaningStatus, 'CLEANING');
  });

  test('bootstrap after app kill recovers committed DB state before relying on Realtime', () async {
    final persisted = _roommaidSession();
    final committedRoom = _room(cleaningStatus: 'CLEANING', version: 2);
    final api = _FakeApiClient(
      verifiedUser: persisted.user,
      roomSnapshots: [
        [committedRoom],
      ],
    );
    final realtime = _FakeRealtimeGateway();
    final controller = AppController(
      apiClient: api,
      sessionStore: _FakeSessionStore(initialSession: persisted),
      realtimeGateway: realtime,
    );
    addTearDown(controller.dispose);

    await controller.bootstrap();

    expect(controller.isAuthenticated, isTrue);
    expect(api.listRoomsCalls, 1);
    expect(controller.rooms.single.cleaningStatus, 'CLEANING');
    expect(controller.rooms.single.version, 2);
    expect(realtime.starts, 1);
  });

  test('bootstrap rejects a persisted session when server role is not ROOMMAID', () async {
    final persisted = _roommaidSession();
    final api = _FakeApiClient(
      verifiedUser: const NovaUser(
        employeeNo: '20002',
        name: '점검자',
        role: 'QM',
        sessionSite: '쏘라노',
      ),
    );
    final store = _FakeSessionStore(initialSession: persisted);
    final realtime = _FakeRealtimeGateway();
    final controller = AppController(
      apiClient: api,
      sessionStore: store,
      realtimeGateway: realtime,
    );
    addTearDown(controller.dispose);

    await controller.bootstrap();

    expect(controller.isAuthenticated, isFalse);
    expect(controller.rooms, isEmpty);
    expect(store.clearCalls, 1);
    expect(realtime.starts, 0);
    expect(controller.globalError, '현재 모바일 알파는 룸메이드 계정만 지원합니다.');
  });
}

NovaSession _roommaidSession() => const NovaSession(
      accessToken: 'test-access-token',
      expiresAt: '2099-01-01T00:00:00Z',
      user: NovaUser(
        employeeNo: '10001',
        name: '테스트',
        role: 'ROOMMAID',
        sessionSite: '쏘라노',
      ),
    );

NovaRoom _room({required String cleaningStatus, required int version}) => NovaRoom(
      businessDate: '2026-09-06',
      site: '쏘라노',
      roomNo: '6514',
      building: '쏘라노',
      roomStatus: 'STAY',
      cleaningStatus: cleaningStatus,
      cleaningType: 'NORMAL',
      assignmentType: 'PRIMARY',
      roommaidEmployeeNo: '10001',
      secondaryRoommaidEmployeeNo: '',
      qmEmployeeNo: '',
      operationalStatus: '',
      version: version,
    );

class _FakeApiClient extends NovaApiClient {
  _FakeApiClient({
    this.loginSession,
    this.verifiedUser,
    List<List<NovaRoom>> roomSnapshots = const [],
    this.mutation,
  }) : roomSnapshots = List<List<NovaRoom>>.from(roomSnapshots);

  final NovaSession? loginSession;
  final NovaUser? verifiedUser;
  final List<List<NovaRoom>> roomSnapshots;
  final Completer<NovaRoomMutationResult>? mutation;
  int listRoomsCalls = 0;

  @override
  Future<NovaSession> login({
    required String name,
    required String employeeNo,
    required String site,
  }) async {
    final value = loginSession;
    if (value == null) throw StateError('loginSession not configured');
    return value;
  }

  @override
  Future<NovaUser> me(String accessToken) async {
    final value = verifiedUser;
    if (value == null) throw StateError('verifiedUser not configured');
    return value;
  }

  @override
  Future<List<NovaRoom>> listRooms({
    required String accessToken,
    required String businessDate,
    required String site,
  }) async {
    if (roomSnapshots.isEmpty) return const [];
    final index = listRoomsCalls < roomSnapshots.length
        ? listRoomsCalls
        : roomSnapshots.length - 1;
    listRoomsCalls += 1;
    return List<NovaRoom>.from(roomSnapshots[index]);
  }

  @override
  Future<NovaRoomMutationResult> mutateRoom({
    required String accessToken,
    required String businessDate,
    required String site,
    required String roomNo,
    required String action,
    required int expectedVersion,
    required String requestId,
  }) {
    final value = mutation;
    if (value == null) throw StateError('mutation not configured');
    return value.future;
  }

  @override
  void close() {}
}

class _FakeRealtimeGateway implements NovaRealtimeGateway {
  int starts = 0;
  int stops = 0;
  int disposals = 0;
  String accessToken = '';
  String site = '';
  Future<void> Function()? onSignal;

  @override
  Future<void> start({
    required String accessToken,
    required String site,
    required Future<void> Function() onSignal,
  }) async {
    starts += 1;
    this.accessToken = accessToken;
    this.site = site;
    this.onSignal = onSignal;
  }

  Future<void> emitSignal() async {
    final callback = onSignal;
    if (callback != null) await callback();
  }

  @override
  Future<void> stop() async {
    stops += 1;
    onSignal = null;
    accessToken = '';
    site = '';
  }

  @override
  void dispose() {
    disposals += 1;
    onSignal = null;
  }
}

class _FakeSessionStore extends SessionStore {
  _FakeSessionStore({NovaSession? initialSession}) : _session = initialSession;

  NovaSession? _session;
  int clearCalls = 0;

  @override
  Future<void> save(NovaSession session) async {
    _session = session;
  }

  @override
  Future<NovaSession?> read() async => _session;

  @override
  Future<void> clear() async {
    clearCalls += 1;
    _session = null;
  }
}
