import { NextRequest, NextResponse } from 'next/server';
import { authenticateRequest } from '@/lib/auth';
import { executeRoomCommand } from '@/lib/room-service';
import { RoomCommandPayload } from '@/lib/types';

export const dynamic = 'force-dynamic';

export async function POST(
  request: NextRequest,
  { params }: { params: { roomNo: string } }
) {
  try {
    const roomNo = params.roomNo;
    const body = await request.json();

    // Authenticate user & RBAC
    let user;
    try {
      user = authenticateRequest(request);
    } catch {
      // Fallback for body role simulation if headers absent
      const role = body.userRole || 'SUPER_ADMIN';
      const employeeNo = body.employeeNo || (role === 'ROOM_MAID' ? '1001' : 'ADMIN-01');
      user = {
        employeeNo,
        name: body.userName || (role === 'ROOM_MAID' ? '김순자' : '관리자'),
        role,
        enabled: true,
        defaultSite: body.site || 'SORA',
        allowedSites: [body.site || 'SORA']
      };
    }

    const {
      businessDate = '2026-09-13',
      site = 'SORA',
      action,
      expectedVersion = 0,
      requestId = `REQ-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      assigneeEmployeeNo,
      operationalNote
    } = body;

    if (!action) {
      return NextResponse.json(
        { ok: false, message: 'action 필드가 필요합니다.' },
        { status: 400 }
      );
    }

    const payload: RoomCommandPayload = {
      businessDate,
      site,
      roomNo,
      action,
      expectedVersion: Number(expectedVersion),
      requestId,
      assigneeEmployeeNo,
      operationalNote
    };

    const result = await executeRoomCommand(payload, user);

    return NextResponse.json(result);
  } catch (error: any) {
    if (error.code === 'VERSION_CONFLICT') {
      return NextResponse.json(
        {
          ok: false,
          code: 'VERSION_CONFLICT',
          message: error.message,
          currentRoom: error.currentRoom
        },
        { status: 409 }
      );
    }

    const isBadRequest =
      error.message.includes('상태에서는') ||
      error.message.includes('권한으로는') ||
      error.message.includes('배정되지 않은');

    return NextResponse.json(
      {
        ok: false,
        code: error.code || 'ACTION_FAILED',
        message: error.message || '작업 처리 중 오류가 발생했습니다.'
      },
      { status: isBadRequest ? 409 : 500 }
    );
  }
}
