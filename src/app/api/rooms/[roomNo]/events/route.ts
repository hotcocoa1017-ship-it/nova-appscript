import { NextRequest, NextResponse } from 'next/server';
import { getDbPool } from '@/lib/db';
import { getMemoryAuditEvents } from '@/lib/room-service';
import { NovaAuditEvent } from '@/lib/types';

export const dynamic = 'force-dynamic';

// Memory events store for fallback
let memoryEvents: NovaAuditEvent[] = [

  {
    id: 1,
    requestId: 'REQ-INIT-001',
    businessDate: '2026-09-13',
    site: 'SORA',
    roomNo: '204',
    action: 'CHANGE_STATUS_CHECKOUT',
    beforeStatus: 'STOCK:NOT_REQUIRED',
    afterStatus: 'CHECKED_OUT:WAITING',
    employeeNo: 'ADMIN-01',
    roomVersion: 1,
    detail: { role: 'SUPER_ADMIN', userName: '총괄관리자', note: '퇴실 처리 완료' },
    createdAt: new Date(Date.now() - 45 * 60 * 1000).toISOString()
  },
  {
    id: 2,
    requestId: 'REQ-INIT-002',
    businessDate: '2026-09-13',
    site: 'SORA',
    roomNo: '206',
    action: 'CLEANING_START',
    beforeStatus: 'CHECKED_OUT:ASSIGNED',
    afterStatus: 'CHECKED_OUT:CLEANING',
    employeeNo: '1001',
    roomVersion: 2,
    detail: { role: 'ROOM_MAID', userName: '김순자', note: '청소 시작' },
    createdAt: new Date(Date.now() - 25 * 60 * 1000).toISOString()
  },
  {
    id: 3,
    requestId: 'REQ-INIT-003',
    businessDate: '2026-09-13',
    site: 'SORA',
    roomNo: '207',
    action: 'CLEANING_COMPLETE',
    beforeStatus: 'CHECKED_OUT:CLEANING',
    afterStatus: 'CHECKED_OUT:QM_WAITING',
    employeeNo: '1001',
    roomVersion: 3,
    detail: { role: 'ROOM_MAID', userName: '김순자', note: '청소 완료 후 점검 요청' },
    createdAt: new Date(Date.now() - 10 * 60 * 1000).toISOString()
  }
];

export async function GET(
  request: NextRequest,
  { params }: { params: { roomNo: string } }
) {
  try {
    const roomNo = params.roomNo;
    const pool = getDbPool();

    if (pool) {
      try {
        const client = await pool.connect();
        try {
          const { rows } = await client.query(
            `SELECT id, request_id, business_date, site, room_no, action,
                    before_status, after_status, employee_no, room_version, detail, created_at
             FROM public.nova_room_events
             WHERE room_no = $1
             ORDER BY created_at DESC
             LIMIT 50`,
            [roomNo]
          );

          if (rows.length > 0) {
            const mapped: NovaAuditEvent[] = rows.map((r: any) => ({
              id: Number(r.id),
              requestId: r.request_id,
              businessDate: r.business_date,
              site: r.site,
              roomNo: r.room_no,
              action: r.action,
              beforeStatus: r.before_status,
              afterStatus: r.after_status,
              employeeNo: r.employee_no,
              roomVersion: Number(r.room_version),
              detail: r.detail,
              createdAt: new Date(r.created_at).toISOString()
            }));

            return NextResponse.json({ ok: true, roomNo, events: mapped });
          }
        } finally {
          client.release();
        }
      } catch (err) {
        console.warn('[DB Event Query Warning, using memory]:', err);
      }
    }

    const liveEvents = getMemoryAuditEvents(roomNo);
    const combined = [...memoryEvents.filter(e => e.roomNo === roomNo), ...liveEvents];
    return NextResponse.json({
      ok: true,
      roomNo,
      events: combined
    });
  } catch (error: any) {
    return NextResponse.json(
      { ok: false, message: error.message || '이력 조회 실패' },
      { status: 500 }
    );
  }
}
