/**
 * NOVA Database Connector & Transaction Manager
 * Supports production PostgreSQL / Supabase pool, with safe fallback and OCC transactions.
 */

import { Pool, PoolClient } from 'pg';
import { RoomEntity, NovaAuditEvent } from './types';

const connectionString = process.env.DATABASE_URL || '';
const hasPgHost = Boolean(process.env.PG_HOST && process.env.PG_USER);

let poolInstance: Pool | null = null;

export function getDbPool(): Pool | null {
  if (poolInstance) return poolInstance;

  if (!connectionString && !hasPgHost) {
    // DATABASE_URL not yet configured
    return null;
  }

  poolInstance = new Pool({
    connectionString: connectionString || undefined,
    host: process.env.PG_HOST || undefined,
    port: Number(process.env.PG_PORT || 5432),
    user: process.env.PG_USER || undefined,
    password: process.env.PG_PASSWORD || undefined,
    database: process.env.PG_DATABASE || 'postgres',
    max: Number(process.env.PG_POOL_MAX || 20),
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 5000,
    ssl: process.env.PG_SSL === 'false' ? false : { rejectUnauthorized: false }
  });

  return poolInstance;
}

/**
 * Executes a callback within a managed database transaction.
 * Automatically performs BEGIN, COMMIT, and ROLLBACK on failure.
 */
export async function withTransaction<T>(
  callback: (client: PoolClient) => Promise<T>
): Promise<T> {
  const pool = getDbPool();
  if (!pool) {
    throw new Error('DATABASE_NOT_CONFIGURED: PostgreSQL 연결 설정이 없습니다.');
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await callback(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    try {
      await client.query('ROLLBACK');
    } catch {
      // rollback error suppressed
    }
    throw error;
  } finally {
    client.release();
  }
}

/**
 * Maps raw PostgreSQL row from `nova_rooms_current` to RoomEntity domain model.
 * Seamlessly provides both legacy NOVA column names and enterprise field aliases.
 */
export function mapRowToRoom(r: Record<string, unknown>): RoomEntity {
  const roomNoStr = String(r.room_no || r.room_number || '');
  const floorCalculated = parseInt(roomNoStr.charAt(0), 10) || 1;
  const startedAt = r.cleaning_started_at || r.started_at ? new Date((r.cleaning_started_at || r.started_at) as string).toISOString() : null;
  const completedAt = r.cleaning_completed_at || r.completed_at ? new Date((r.cleaning_completed_at || r.completed_at) as string).toISOString() : null;
  const inspectedAt = r.inspected_at ? new Date(r.inspected_at as string).toISOString() : null;
  const maidId = r.roommaid_employee_no || r.assigned_worker ? String(r.roommaid_employee_no || r.assigned_worker) : null;
  const qmId = r.qm_employee_no || r.assigned_qm ? String(r.qm_employee_no || r.assigned_qm) : null;
  const inspectorId = r.inspector_employee_no || r.assigned_inspector ? String(r.inspector_employee_no || r.assigned_inspector) : null;

  return {
    id: r.id ? String(r.id) : undefined,
    roomId: r.id ? String(r.id) : undefined,
    businessDate: r.business_date instanceof Date
      ? r.business_date.toISOString().slice(0, 10)
      : String(r.business_date || ''),
    site: String(r.site || ''),
    roomNo: roomNoStr,
    roomNumber: roomNoStr,
    building: String(r.building || `${floorCalculated}동`),
    floor: Number(r.floor || floorCalculated),
    roomType: String(r.room_type || 'Standard'),
    roomStatus: (r.room_status as any) || 'STOCK',
    cleaningStatus: (r.cleaning_status as any) || 'WAITING',
    inspectionStatus: (r.cleaning_status as any) || 'WAITING',
    cleaningType: (r.cleaning_type as any) || 'NORMAL',
    assignmentType: (r.assignment_type as any) || 'SOLO',
    roommaidEmployeeNo: maidId,
    assignedWorker: maidId,
    secondaryRoommaidEmployeeNo: r.secondary_roommaid_employee_no ? String(r.secondary_roommaid_employee_no) : null,
    qmEmployeeNo: qmId,
    assignedQm: qmId,
    assignedInspector: inspectorId,
    operationalStatus: String(r.operational_status || ''),
    version: Number(r.version || 1),
    cleaningStartedAt: startedAt,
    startedAt,
    cleaningCompletedAt: completedAt,
    completedAt,
    inspectedAt,
    updatedBy: r.updated_by ? String(r.updated_by) : undefined,
    updatedAt: r.updated_at ? new Date(r.updated_at as string).toISOString() : undefined,
  };
}
