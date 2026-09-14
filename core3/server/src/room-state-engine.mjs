export const CleaningStatus = Object.freeze({
  WAITING: 'WAITING',
  ASSIGNED: 'ASSIGNED',
  CLEANING: 'CLEANING',
  COMPLETED: 'COMPLETED',
  QM_WAITING: 'QM_WAITING',
  QM_CHECKING: 'QM_CHECKING',
  QM_COMPLETED: 'QM_COMPLETED',
  REWORK: 'REWORK',
  NOT_REQUIRED: 'NOT_REQUIRED',
});

export const RoomAction = Object.freeze({
  CLEANING_START: 'CLEANING_START',
  CLEANING_COMPLETE: 'CLEANING_COMPLETE',
});

export class RoomStateConflict extends Error {
  constructor(code, message, current) {
    super(message);
    this.name = 'RoomStateConflict';
    this.code = code;
    this.current = current;
  }
}

const STARTABLE = new Set([
  CleaningStatus.WAITING,
  CleaningStatus.ASSIGNED,
  CleaningStatus.REWORK,
]);

const COMPLETE_ALREADY_ACHIEVED = new Set([
  CleaningStatus.COMPLETED,
  CleaningStatus.QM_WAITING,
  CleaningStatus.QM_CHECKING,
  CleaningStatus.QM_COMPLETED,
]);

function normalize(value) {
  return String(value ?? '').trim().toUpperCase();
}

function requireRoom(room) {
  if (!room || typeof room !== 'object') {
    throw new TypeError('room is required');
  }
  if (!String(room.businessDate ?? '').trim() || !String(room.site ?? '').trim() || !String(room.roomNo ?? '').trim()) {
    throw new TypeError('businessDate, site and roomNo are required');
  }
  return {
    ...room,
    roomStatus: normalize(room.roomStatus),
    cleaningStatus: normalize(room.cleaningStatus),
    version: Number(room.version ?? 0),
    qmEmployeeNo: String(room.qmEmployeeNo ?? '').trim(),
  };
}

function assertExpectedVersion(room, expectedVersion) {
  if (expectedVersion > 0 && expectedVersion !== room.version) {
    throw new RoomStateConflict(
      'VERSION_CONFLICT',
      `${room.roomNo}호의 최신 상태가 변경되었습니다. 서버 상태로 다시 동기화합니다.`,
      room,
    );
  }
}

/**
 * Pure NOVA Core room-state decision function.
 *
 * Authentication, row locking, idempotency claims, event/outbox insertion and
 * persistence belong to the transaction boundary. This function only decides
 * the transition after the authoritative row has been locked and loaded.
 *
 * Important: identical intent convergence is evaluated before expectedVersion.
 * If another valid request has already achieved START or COMPLETE, a stale
 * caller should converge to success instead of showing a false concurrency
 * error. Real conflicting intent still requires a matching latest version.
 */
export function decideRoomCleaningAction(roomInput, actionInput, options = {}) {
  const room = requireRoom(roomInput);
  const action = normalize(actionInput);
  const expectedVersion = Number(options.expectedVersion ?? 0);

  if (action === RoomAction.CLEANING_START) {
    if (room.cleaningStatus === CleaningStatus.CLEANING) {
      return {
        changed: false,
        alreadyApplied: true,
        beforeStatus: room.cleaningStatus,
        afterStatus: room.cleaningStatus,
      };
    }

    assertExpectedVersion(room, expectedVersion);

    // Preserve the existing NOVA rule: DUE_OUT cannot newly enter CLEANING.
    if (room.roomStatus === 'DUE_OUT') {
      throw new RoomStateConflict(
        'DUE_OUT_BLOCKED',
        `${room.roomNo}호는 아직 퇴실 전 상태입니다.`,
        room,
      );
    }

    if (!STARTABLE.has(room.cleaningStatus)) {
      throw new RoomStateConflict(
        'INVALID_CLEANING_STATE',
        `${room.roomNo}호는 현재 ${room.cleaningStatus || 'UNKNOWN'} 상태에서 청소를 시작할 수 없습니다.`,
        room,
      );
    }

    return {
      changed: true,
      alreadyApplied: false,
      beforeStatus: room.cleaningStatus,
      afterStatus: CleaningStatus.CLEANING,
    };
  }

  if (action === RoomAction.CLEANING_COMPLETE) {
    if (COMPLETE_ALREADY_ACHIEVED.has(room.cleaningStatus)) {
      return {
        changed: false,
        alreadyApplied: true,
        beforeStatus: room.cleaningStatus,
        afterStatus: room.cleaningStatus,
      };
    }

    assertExpectedVersion(room, expectedVersion);

    if (room.cleaningStatus !== CleaningStatus.CLEANING) {
      throw new RoomStateConflict(
        'INVALID_CLEANING_STATE',
        `${room.roomNo}호는 현재 ${room.cleaningStatus || 'UNKNOWN'} 상태에서 청소완료할 수 없습니다.`,
        room,
      );
    }

    return {
      changed: true,
      alreadyApplied: false,
      beforeStatus: room.cleaningStatus,
      afterStatus: room.qmEmployeeNo ? CleaningStatus.QM_WAITING : CleaningStatus.COMPLETED,
    };
  }

  throw new RoomStateConflict(
    'UNSUPPORTED_ACTION',
    `지원하지 않는 객실 작업입니다. (${action || 'EMPTY'})`,
    room,
  );
}
