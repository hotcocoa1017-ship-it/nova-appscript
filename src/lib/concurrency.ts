/**
 * NOVA Concurrency & Idempotency Engine
 * Optimistic Concurrency Control (version checking), Pessimistic Row Locking, and Idempotent Request Dedup.
 */

import { PoolClient } from 'pg';
import { CommandResponse, NovaAuditEvent, NovaUser, RoomCommandPayload, RoomEntity } from './types';
import { mapRowToRoom } from './db';
import { validateStateTransition } from './state-machine';

export class ConcurrencyConflictError extends Error {
  code: string;
  currentRoom: RoomEntity;

  constructor(message: string, currentRoom: RoomEntity) {
    super(message);
    this.name = 'ConcurrencyConflictError';
    this.code = 'VERSION_CONFLICT';
    this.currentRoom = currentRoom;
  }
}

/**
 * Handles room action atomically with:
 * 1. Request deduplication (Idempotency)
 * 2. Pessimistic lock (SELECT ... FOR UPDATE)
 * 3. Optimistic version check
 * 4. State transition validation
 * 5. Update room record (increment version)
 * 6. Record audit event
 * 7. Cache deduplication response
 */
export async function executeRoomActionTransactional(
  client: PoolClient,
  payload: RoomCommandPayload,
  user: NovaUser
): Promise<CommandResponse<RoomEntity>> {
  const startedAt = Date.now();
  const { businessDate, site, roomNo, action, expectedVersion, requestId } = payload;

  // 1. Idempotency Check (nova_request_dedup)
  const dedupInsert = await client.query(
    `INSERT INTO public.nova_request_dedup (request_id, employee_no, action)
     VALUES ($1, $2, $3)
     ON CONFLICT (request_id) DO NOTHING
     RETURNING request_id`,
    [requestId, user.employeeNo, action]
  );

  if (dedupInsert.rowCount === 0) {
    // Already processed or in progress
    const prior = await client.query(
      `SELECT response_json FROM public.nova_request_dedup WHERE request_id = $1`,
      [requestId]
    );
    if (prior.rows[0]?.response_json) {
      const cached = prior.rows[0].response_json as CommandResponse<RoomEntity>;
      return {
        ...cached,
        duplicateRequest: true,
        timingMs: Date.now() - startedAt
      };
    }
    throw new Error('동일한 작업 요청이 이미 처리 중입니다.');
  }

  // 2. Pessimistic Row Lock (FOR UPDATE)
  const roomQuery = await client.query(
    `SELECT * FROM public.nova_rooms_current
     WHERE business_date = $1 AND site = $2 AND room_no = $3
     FOR UPDATE`,
    [businessDate, site, roomNo]
  );

  if (roomQuery.rowCount === 0) {
    throw new Error(`객실(${roomNo})을 찾을 수 없습니다.`);
  }

  const currentRoom = mapRowToRoom(roomQuery.rows[0]);

  // 3. Optimistic Concurrency Control (Version Verification)
  if (expectedVersion > 0 && expectedVersion !== currentRoom.version) {
    throw new ConcurrencyConflictError(
      `${roomNo}호 객실 상태가 다른 사용자의 작업으로 인해 먼저 변경되었습니다. 최신 정보를 불러옵니다.`,
      currentRoom
    );
  }

  // 4. State Machine Validation
  const validation = validateStateTransition(currentRoom, action, user);
  if (!validation.valid) {
    throw new Error(validation.errorMessage || '허용되지 않는 객실 상태 전환입니다.');
  }

  // 5. Compute State Changes
  const nextRoomStatus = validation.nextRoomStatus || currentRoom.roomStatus;
  const nextCleaningStatus = validation.nextCleaningStatus || currentRoom.cleaningStatus;
  const beforeStatus = `${currentRoom.roomStatus}:${currentRoom.cleaningStatus}`;
  const afterStatus = `${nextRoomStatus}:${nextCleaningStatus}`;

  const cleaningStartedAtSql = nextCleaningStatus === 'CLEANING'
    ? 'COALESCE(cleaning_started_at, NOW())'
    : 'cleaning_started_at';
  const cleaningCompletedAtSql = nextCleaningStatus === 'QM_WAITING' || nextCleaningStatus === 'COMPLETED'
    ? 'NOW()'
    : 'cleaning_completed_at';

  const updateResult = await client.query(
    `UPDATE public.nova_rooms_current
     SET room_status = $4,
         cleaning_status = $5,
         version = version + 1,
         cleaning_started_at = ${cleaningStartedAtSql},
         cleaning_completed_at = ${cleaningCompletedAtSql},
         updated_by = $6,
         updated_at = NOW()
     WHERE business_date = $1 AND site = $2 AND room_no = $3
     RETURNING *`,
    [businessDate, site, roomNo, nextRoomStatus, nextCleaningStatus, user.employeeNo]
  );

  const updatedRoom = mapRowToRoom(updateResult.rows[0]);

  // 6. Record Audit Event (nova_room_events)
  await client.query(
    `INSERT INTO public.nova_room_events (
       request_id, business_date, site, room_no, action,
       before_status, after_status, employee_no, room_version, detail
     ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)`,
    [
      requestId,
      businessDate,
      site,
      roomNo,
      action,
      beforeStatus,
      afterStatus,
      user.employeeNo,
      updatedRoom.version,
      JSON.stringify({
        role: user.role,
        userName: user.name,
        operationalNote: payload.operationalNote || null,
        photos: payload.photos || null
      })
    ]
  );

  // 7. Store Cached Response for Idempotency
  const response: CommandResponse<RoomEntity> = {
    ok: true,
    data: updatedRoom,
    version: updatedRoom.version,
    requestId,
    timingMs: Date.now() - startedAt
  };

  await client.query(
    `UPDATE public.nova_request_dedup
     SET response_json = $2::jsonb
     WHERE request_id = $1`,
    [requestId, JSON.stringify(response)]
  );

  return response;
}
