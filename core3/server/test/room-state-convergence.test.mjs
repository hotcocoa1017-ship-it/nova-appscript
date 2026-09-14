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
    version: 9,
    qmEmployeeNo: '',
    ...overrides,
  };
}

test('START already achieved converges before stale expectedVersion check', () => {
  const result = decideRoomCleaningAction(
    room({ cleaningStatus: CleaningStatus.CLEANING, version: 12 }),
    RoomAction.CLEANING_START,
    { expectedVersion: 3 },
  );
  assert.equal(result.changed, false);
  assert.equal(result.alreadyApplied, true);
  assert.equal(result.afterStatus, CleaningStatus.CLEANING);
});

for (const state of [
  CleaningStatus.COMPLETED,
  CleaningStatus.QM_WAITING,
  CleaningStatus.QM_CHECKING,
  CleaningStatus.QM_COMPLETED,
]) {
  test(`COMPLETE already achieved at ${state} converges before stale version check`, () => {
    const result = decideRoomCleaningAction(
      room({ cleaningStatus: state, version: 12 }),
      RoomAction.CLEANING_COMPLETE,
      { expectedVersion: 3 },
    );
    assert.equal(result.changed, false);
    assert.equal(result.alreadyApplied, true);
  });
}

test('real conflicting intent still enforces expectedVersion', () => {
  assert.throws(
    () => decideRoomCleaningAction(
      room({ cleaningStatus: CleaningStatus.WAITING, version: 12 }),
      RoomAction.CLEANING_START,
      { expectedVersion: 3 },
    ),
    error => error instanceof RoomStateConflict && error.code === 'VERSION_CONFLICT',
  );
});
