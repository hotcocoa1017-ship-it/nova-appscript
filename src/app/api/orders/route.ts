import { NextRequest, NextResponse } from 'next/server';
import { selectBestHouseman } from '@/lib/houseman-engine';
import { HousemanOrder } from '@/lib/types';

export const dynamic = 'force-dynamic';

// Memory orders store for resilient operation
let memoryOrders: HousemanOrder[] = [
  {
    orderId: 'ORD-801',
    businessDate: '2026-09-13',
    site: 'SORA',
    roomNo: '304',
    category: 'TOWEL',
    items: [{ name: '배스타월', quantity: 2 }],
    itemSummary: '배스타월 2장',
    quantity: 2,
    requester: '프론트',
    assignedEmployeeNo: 'hm-3',
    assignedName: '한지훈 (3F)',
    status: 'PROCESSING',
    important: false,
    version: 1,
    registeredBy: 'ADMIN-01',
    registeredAt: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
    startedAt: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    updatedAt: new Date().toISOString()
  },
  {
    orderId: 'ORD-802',
    businessDate: '2026-09-13',
    site: 'SORA',
    roomNo: '512',
    category: 'AMENITY',
    items: [{ name: '생수', quantity: 2 }],
    itemSummary: '생수 2병',
    quantity: 2,
    requester: '고객직접',
    assignedEmployeeNo: 'hm-2',
    assignedName: '정태양 (5F)',
    status: 'COMPLETED',
    important: false,
    version: 2,
    registeredBy: 'ADMIN-01',
    registeredAt: new Date(Date.now() - 40 * 60 * 1000).toISOString(),
    startedAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    completedAt: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
    updatedAt: new Date().toISOString()
  }
];

export async function GET(request: NextRequest) {
  return NextResponse.json({
    ok: true,
    count: memoryOrders.length,
    orders: memoryOrders
  });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const {
      roomNo,
      category = 'TOWEL',
      itemSummary,
      quantity = 1,
      requester = '프론트',
      manualHousemanId,
      important = false,
      note = ''
    } = body;

    if (!roomNo || !itemSummary) {
      return NextResponse.json(
        { ok: false, message: '객실번호와 요청 항목은 필수입니다.' },
        { status: 400 }
      );
    }

    const targetFloor = parseInt(String(roomNo).charAt(0), 10) || 2;

    let assignedId = manualHousemanId;
    let assignedName = '';

    if (!assignedId) {
      const best = selectBestHouseman(targetFloor, category);
      assignedId = best.houseman.id;
      assignedName = `${best.houseman.name} (${best.houseman.currentFloor}F)`;
    }

    const newOrder: HousemanOrder = {
      orderId: `ORD-${Date.now().toString().slice(-4)}`,
      businessDate: '2026-09-13',
      site: 'SORA',
      roomNo: String(roomNo),
      category,
      items: [{ name: itemSummary, quantity: Number(quantity) }],
      itemSummary,
      quantity: Number(quantity),
      requester,
      assignedEmployeeNo: assignedId,
      assignedName,
      status: 'ASSIGNED',
      important: Boolean(important),
      note,
      version: 1,
      registeredBy: 'ADMIN-01',
      registeredAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };

    memoryOrders.unshift(newOrder);

    return NextResponse.json({
      ok: true,
      order: newOrder
    });
  } catch (error: any) {
    return NextResponse.json(
      { ok: false, message: error.message || '오더 등록 실패' },
      { status: 500 }
    );
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json();
    const { orderId, status, unableReason } = body;

    const order = memoryOrders.find(o => o.orderId === orderId);
    if (!order) {
      return NextResponse.json(
        { ok: false, message: '오더를 찾을 수 없습니다.' },
        { status: 404 }
      );
    }

    order.status = status;
    order.version += 1;
    order.updatedAt = new Date().toISOString();

    if (status === 'ACCEPTED') {
      order.acceptedAt = new Date().toISOString();
    } else if (status === 'PROCESSING') {
      order.startedAt = new Date().toISOString();
    } else if (status === 'COMPLETED') {
      order.completedAt = new Date().toISOString();
    } else if (status === 'UNABLE') {
      order.unableReason = unableReason || '사유 미입력';
    }

    return NextResponse.json({
      ok: true,
      order
    });
  } catch (error: any) {
    return NextResponse.json(
      { ok: false, message: error.message || '오더 상태 변경 실패' },
      { status: 500 }
    );
  }
}
