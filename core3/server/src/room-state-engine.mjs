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

/**
 * Pure NOVA Core room-state decision function.
 *
 * This function does not perform authentication, DB locking, idempotency-key
 * claiming, event insertion or persistence. Those are transaction boundary
 * responsibilities. It only decides the permitted state transition after the
 * authoritative row has been locked and loaded.
 */
export function decideRoomCleaningAction(roomInput, actionInput, options = {}) {
  const room = requireRoom(roomInput);
  const action = normalize(actionInput);
  const expectedVersion = Number(options.expectedVersion ?? 0);

  if (expectedVersion > 0 && expectedVersion !== room.version) {
    throw new RoomStateConflict(
      'VERSION_CONFLICT',
      `${room.roomNo}호의 최신 상태가 변경되었습니다. 최신 상태로 다시 확인합니다.`,
      room,
    );
  }

  if (action === RoomAction.CLEANING_START) {
    // Preserve the current NOVA rule: a DUE_OUT room must not start cleaning
    // until the authoritative room status has changed to a startable state.
    if (room.roomStatus === 'DUE_OUT') {
      throw new RoomStateConflict(
        'DUE_OUT_BLOCKED',
        `${room.roomNo}호는 아직 퇴실 전 상태입니다.`,
        room,
      );
    }

    // A different request ID arriving while already CLEANING is treated as an
    // achieved identical intent. Exact request replays are handled earlier by
    // the DB idempotency record and return the original committed response.
    if (room.cleaningStatus === CleaningStatus.CLEANING) {
      return {
        changed: false,
        alreadyApplied: true,
        beforeStatus: room.cleaningStatus,
        afterStatus: room.cleaningStatus,
      };
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
