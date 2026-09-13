/**
 * NOVA Room Service Layer
 * Bridges database operations with OCC, Idempotency, and safe fallback storage.
 */

import { executeRoomActionTransactional } from './concurrency';
import { getDbPool, mapRowToRoom, withTransaction } from './db';
import { validateStateTransition } from './state-machine';
import { CommandResponse, NovaUser, RoomCommandPayload, RoomEntity } from './types';

// In-Memory Fallback Store (Used when PostgreSQL connection is not active)
let memoryRooms: RoomEntity[] = [];
const memoryDedupMap = new Map<string, CommandResponse<RoomEntity>>();
const memoryAuditEvents: any[] = [];

export function initializeMemoryRooms(): RoomEntity[] {
  if (memoryRooms.length > 0) return memoryRooms;

  const floors = [2, 3, 4, 5, 6];
  const roomTypes = ['Standard Double', 'Standard Twin', 'Deluxe King', 'Executive Suite'];
  const rooms: RoomEntity[] = [];

  floors.forEach(floor => {
    for (let r = 1; r <= 12; r++) {
      const roomNo = `${floor}${r < 10 ? '0' + r : r}`;
      const typeIndex = (floor + r) % roomTypes.length;
      const roomType = roomTypes[typeIndex];
      const seed = (floor * 17 + r * 11) % 12;

      let roomStatus: RoomEntity['roomStatus'] = 'STOCK';
      let cleaningStatus: RoomEntity['cleaningStatus'] = 'COMPLETED';
      let guestName = '';
      let housekeeperId: string | null = null;
      let qmId: string | null = null;
      let operationalStatus = '';
      const dnd = (r === 3 || r === 9);

      if (roomNo === '308' || roomNo === '505') {
        roomStatus = 'OOO';
        cleaningStatus = 'NOT_REQUIRED';
        operationalStatus = roomNo === '308' ? '욕실 세면대 수전 누수 점검 중' : '에어컨 냉매 교체 필요';
      } else if (seed <= 4) {
        roomStatus = 'STOCK';
        guestName = ['김민수', '이서연', 'Park Smith', 'Tanaka Ken', '정다은', '최현우', 'Sarah Jenkins'][r % 7];
        cleaningStatus = (seed === 1) ? 'CLEANING' : 'NOT_REQUIRED';
        housekeeperId = (floor <= 3) ? '1001' : '1003';
      } else if (seed === 5 || seed === 6) {
        roomStatus = 'CHECKED_OUT';
        cleaningStatus = 'WAITING';
      } else if (seed === 7) {
        roomStatus = 'CHECKED_OUT';
        cleaningStatus = 'CLEANING';
        housekeeperId = (floor <= 4) ? '1002' : '1004';
      } else if (seed === 8) {
        roomStatus = 'CHECKED_OUT';
        cleaningStatus = 'QM_WAITING';
        housekeeperId = (floor <= 4) ? '1002' : '1003';
        qmId = '2001';
      } else {
        roomStatus = 'VACANT_CLEAN';
        cleaningStatus = 'QM_COMPLETED';
        qmId = '2001';
      }

      rooms.push({
        businessDate: '2026-09-13',
        site: 'SORA',
        roomNo,
        building: `${floor}동`,
        floor,
        roomType,
        roomStatus,
        cleaningStatus,
        cleaningType: 'NORMAL',
        assignmentType: 'SOLO',
        roommaidEmployeeNo: housekeeperId,
        roommaidName: housekeeperId === '1001' ? '김순자' : housekeeperId === '1002' ? '박영희' : housekeeperId === '1003' ? '이정숙' : housekeeperId === '1004' ? '최미경' : null,
        qmEmployeeNo: qmId,
        qmName: qmId ? '강QM' : null,
        operationalStatus,
        dnd,
        guestName,
        checkOutTime: '11:00',
        version: 1,
        updatedAt: new Date().toISOString()
      });
    }
  });

  memoryRooms = rooms;
  return memoryRooms;
}

/**
 * Fetch all rooms for site and businessDate
 */
export async function getRoomsForSite(businessDate: string, site: string, user: NovaUser): Promise<RoomEntity[]> {
  const pool = getDbPool();

  if (pool) {
    try {
      const client = await pool.connect();
      try {
        let sql = `SELECT * FROM public.nova_rooms_current WHERE business_date = $1 AND site = $2`;
        const params: any[] = [businessDate, site];

        if (user.role === 'ROOM_MAID') {
          sql += ` AND (roommaid_employee_no = $3 OR secondary_roommaid_employee_no = $3)`;
          params.push(user.employeeNo);
        } else if (user.role === 'QM') {
          sql += ` AND qm_employee_no = $3`;
          params.push(user.employeeNo);
        }

        sql += ` ORDER BY room_no ASC`;
        const { rows } = await client.query(sql, params);
        if (rows.length > 0) {
          return rows.map(mapRowToRoom);
        }
      } finally {
        client.release();
      }
    } catch (err) {
      console.warn('[DB Query Warning, falling back to memory state]:', err);
    }
  }

  // Fallback memory state
  const all = initializeMemoryRooms();
  let filtered = all.filter(r => r.site === site && r.businessDate === businessDate);

  if (user.role === 'ROOM_MAID') {
    filtered = filtered.filter(r => r.roommaidEmployeeNo === user.employeeNo || r.secondaryRoommaidEmployeeNo === user.employeeNo);
  } else if (user.role === 'QM') {
    filtered = filtered.filter(r => r.qmEmployeeNo === user.employeeNo);
  }

  return filtered;
}

/**
 * Executes a room action command with OCC & Idempotency.
 */
export async function executeRoomCommand(
  payload: RoomCommandPayload,
  user: NovaUser
): Promise<CommandResponse<RoomEntity>> {
  const pool = getDbPool();

  if (pool) {
    try {
      return await withTransaction(async (client) => {
        return await executeRoomActionTransactional(client, payload, user);
      });
    } catch (err: any) {
      if (err.code === 'VERSION_CONFLICT') {
        throw err;
      }
      console.warn('[Postgres Transaction Failed, falling back to Memory OCC Engine]:', err.message);
    }
  }

  // In-Memory OCC & Idempotency Engine
  const startedAt = Date.now();
  const { roomNo, action, expectedVersion, requestId } = payload;

  // 1. Dedup check
  if (memoryDedupMap.has(requestId)) {
    const prior = memoryDedupMap.get(requestId)!;
    return { ...prior, duplicateRequest: true, timingMs: Date.now() - startedAt };
  }

  // 2. Find room
  const rooms = initializeMemoryRooms();
  const roomIndex = rooms.findIndex(r => r.roomNo === roomNo);
  if (roomIndex === -1) {
    throw new Error(`객실(${roomNo})을 찾을 수 없습니다.`);
  }

  const currentRoom = rooms[roomIndex];

  // 3. Version check (OCC)
  if (expectedVersion > 0 && expectedVersion !== currentRoom.version) {
    const error: any = new Error(`${roomNo}호 객실 상태가 다른 사용자에 의해 먼저 변경되었습니다.`);
    error.code = 'VERSION_CONFLICT';
    error.currentRoom = currentRoom;
    throw error;
  }

  // 4. Validate transition
  const validation = validateStateTransition(currentRoom, action, user);
  if (!validation.valid) {
    throw new Error(validation.errorMessage || '허용되지 않는 객실 작업입니다.');
  }

  // 5. Update room
  let assignedMaidNo = currentRoom.roommaidEmployeeNo;
  let assignedMaidName = currentRoom.roommaidName;
  if (action === 'ASSIGN_ROOMMAID' && payload.assigneeEmployeeNo) {
    assignedMaidNo = payload.assigneeEmployeeNo;
    assignedMaidName = payload.assigneeEmployeeNo === '1001' ? '김순자' :
      payload.assigneeEmployeeNo === '1002' ? '박영희' :
      payload.assigneeEmployeeNo === '1003' ? '이정숙' :
      payload.assigneeEmployeeNo === '1004' ? '최미경' : '배정직원';
  }

  let assignedQmNo = currentRoom.qmEmployeeNo;
  let assignedQmName = currentRoom.qmName;
  if (action === 'QM_ASSIGN' && payload.assigneeEmployeeNo) {
    assignedQmNo = payload.assigneeEmployeeNo;
    assignedQmName = payload.assigneeEmployeeNo === 'QM-2001' ? '강QM' : '인스펙터';
  } else if (action === 'QM_UNASSIGN') {
    assignedQmNo = null;
    assignedQmName = null;
  }

  const nextRoom: RoomEntity = {
    ...currentRoom,
    roomStatus: validation.nextRoomStatus || currentRoom.roomStatus,
    cleaningStatus: validation.nextCleaningStatus || currentRoom.cleaningStatus,
    roommaidEmployeeNo: assignedMaidNo,
    roommaidName: assignedMaidName,
    qmEmployeeNo: assignedQmNo,
    qmName: assignedQmName,
    version: currentRoom.version + 1,
    cleaningStartedAt: validation.nextCleaningStatus === 'CLEANING' ? (currentRoom.cleaningStartedAt || new Date().toISOString()) : currentRoom.cleaningStartedAt,
    cleaningCompletedAt: (validation.nextCleaningStatus === 'QM_WAITING' || validation.nextCleaningStatus === 'COMPLETED') ? new Date().toISOString() : currentRoom.cleaningCompletedAt,
    updatedBy: user.employeeNo,
    updatedAt: new Date().toISOString()
  };

  rooms[roomIndex] = nextRoom;

  // 6. Audit
  memoryAuditEvents.push({
    id: memoryAuditEvents.length + 10,
    requestId,
    businessDate: payload.businessDate || currentRoom.businessDate,
    site: payload.site || currentRoom.site,
    roomNo,
    action,
    beforeStatus: `${currentRoom.roomStatus}:${currentRoom.cleaningStatus}`,
    afterStatus: `${nextRoom.roomStatus}:${nextRoom.cleaningStatus}`,
    employeeNo: user.employeeNo,
    roomVersion: nextRoom.version,
    detail: { userName: user.name, role: user.role, note: payload.operationalNote || '' },
    createdAt: new Date().toISOString()
  });

  const response: CommandResponse<RoomEntity> = {
    ok: true,
    data: nextRoom,
    version: nextRoom.version,
    requestId,
    timingMs: Date.now() - startedAt
  };

  memoryDedupMap.set(requestId, response);
  return response;
}

/**
 * Returns recorded audit events for fallback/in-memory mode
 */
export function getMemoryAuditEvents(roomNo: string) {
  return memoryAuditEvents.filter(e => e.roomNo === roomNo);
}

