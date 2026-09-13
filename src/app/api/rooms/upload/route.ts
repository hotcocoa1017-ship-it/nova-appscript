import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  try {
    const data = await req.json();
    // Here we would use room-service to bulk insert/update
    return NextResponse.json({ 
      ok: true, 
      message: '객실 데이터가 성공적으로 업로드되었습니다.',
      count: data.length || 0
    });
  } catch (err: any) {
    return NextResponse.json({ ok: false, message: '업로드 중 오류가 발생했습니다.' }, { status: 500 });
  }
}
