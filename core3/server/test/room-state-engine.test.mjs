import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CleaningStatus,
  RoomAction,
  RoomStateConflict,
  decideRoomCleaningAction,
} from '../src/room-state-engine.mjs';

function room(overrides = {}) {
  return {
    businessDate: '2026-09-06',
    site: '쏘라노',
    roomNo: '7217',
    roomStatus: 'CHECKED_OUT',
    cleaningStatus: CleaningStatus.WAITING,
    version: 1,
    qmEmployeeNo: '',
    ...overrides,
  };
}

for (const state of [CleaningStatus.WAITING, CleaningStatus.ASSIGNED, CleaningStatus.REWORK]) {
  test(`START permits ${state} -> CLEANING`, () => {
    const result = decideRoomCleaningAction(room({ cleaningStatus: state }), RoomAction.CLEANING_START);
    assert.deepEqual(result, {
      changed: true,
      alreadyApplied: false,
      beforeStatus: state,
      afterStatus: CleaningStatus.CLEANING,
    });
  });
}

test('START on CLEANING converges as already applied', () => {
  const result = decideRoomCleaningAction(room({ cleaningStatus: CleaningStatus.CLEANING }), RoomAction.CLEANING_START);
  assert.equal(result.changed, false);
  assert.equal(result.alreadyApplied, true);
  assert.equal(result.afterStatus, CleaningStatus.CLEANING);
});

test('START blocks DUE_OUT before cleaning-state transition', () => {
  assert.throws(
    () => decideRoomCleaningAction(room({ roomStatus: 'DUE_OUT', cleaningStatus: CleaningStatus.ASSIGNED }), RoomAction.CLEANING_START),
    error => error instanceof RoomStateConflict && error.code === 'DUE_OUT_BLOCKED',
  );
});

test('START blocks a completed room for a new request', () => {
  assert.throws(
    () => decideRoomCleaningAction(room({ cleaningStatus: CleaningStatus.COMPLETED }), RoomAction.CLEANING_START),
    error => error instanceof RoomStateConflict && error.code === 'INVALID_CLEANING_STATE',
  );
});

test('COMPLETE changes CLEANING -> COMPLETED without QM', () => {
  const result = decideRoomCleaningAction(room({ cleaningStatus: CleaningStatus.CLEANING }), RoomAction.CLEANING_COMPLETE);
  assert.equal(result.changed, true);
  assert.equal(result.afterStatus, CleaningStatus.COMPLETED);
});

test('COMPLETE changes CLEANING -> QM_WAITING when QM is assigned', () => {
  const result = decideRoomCleaningAction(
    room({ cleaningStatus: CleaningStatus.CLEANING, qmEmployeeNo: '308680' }),
    RoomAction.CLEANING_COMPLETE,
  );
  assert.equal(result.changed, true);
  assert.equal(result.afterStatus, CleaningStatus.QM_WAITING);
});

for (const state of [
  CleaningStatus.COMPLETED,
  CleaningStatus.QM_WAITING,
  CleaningStatus.QM_CHECKING,
  CleaningStatus.QM_COMPLETED,
]) {
  test(`COMPLETE on ${state} converges as already achieved`, () => {
    const result = decideRoomCleaningAction(room({ cleaningStatus: state }), RoomAction.CLEANING_COMPLETE);
    assert.equal(result.changed, false);
    assert.equal(result.alreadyApplied, true);
  });
}

test('COMPLETE rejects WAITING', () => {
  assert.throws(
    () => decideRoomCleaningAction(room({ cleaningStatus: CleaningStatus.WAITING }), RoomAction.CLEANING_COMPLETE),
    error => error instanceof RoomStateConflict && error.code === 'INVALID_CLEANING_STATE',
  );
});

test('expectedVersion mismatch is a real version conflict', () => {
  assert.throws(
    () => decideRoomCleaningAction(room({ version: 7 }), RoomAction.CLEANING_START, { expectedVersion: 6 }),
    error => error instanceof RoomStateConflict && error.code === 'VERSION_CONFLICT' && error.current.version === 7,
  );
});

test('matching expectedVersion proceeds', () => {
  const result = decideRoomCleaningAction(room({ version: 7 }), RoomAction.CLEANING_START, { expectedVersion: 7 });
  assert.equal(result.afterStatus, CleaningStatus.CLEANING);
});

test('unsupported action is rejected explicitly', () => {
  assert.throws(
    () => decideRoomCleaningAction(room(), 'DELETE_ROOM'),
    error => error instanceof RoomStateConflict && error.code === 'UNSUPPORTED_ACTION',
  );
});
