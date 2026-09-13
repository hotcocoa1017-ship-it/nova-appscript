// scripts/e2e-server-test.mjs
// E2E HTTP API & Real Server Verification for NOVA RMS

const BASE_URL = 'http://localhost:3000';

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  const data = await res.json().catch(() => null);
  return { status: res.status, data, ok: res.ok };
}

async function runE2ETests() {
  console.log('====================================================');
  console.log('?? NOVA RMS - LIVE SERVER E2E VERIFICATION SUITE');
  console.log('Target: ' + BASE_URL);
  console.log('====================================================\n');

  let passed = 0;
  let failed = 0;

  function assert(condition, name, details = '') {
    if (condition) {
      console.log(` ? PASS: ${name}`);
      passed++;
    } else {
      console.error(` ? FAIL: ${name} - ${details}`);
      failed++;
    }
  }

  // 1. Root Page HTTP 200
  try {
    const rootRes = await fetch(BASE_URL);
    assert(rootRes.status === 200, '1. 메인 웹 대시보드 진입 (GET / -> 200 OK)');
  } catch (err) {
    assert(false, '1. 메인 웹 대시보드 진입', err.message);
  }

  // 2. Room List API
  const roomsRes = await request('/api/rooms');
  const roomsList = roomsRes.data?.rooms || [];
  assert(roomsRes.ok && Array.isArray(roomsList) && roomsList.length >= 60, 
    `2. 전체 객실 데이터 실시간 조회 (GET /api/rooms -> ${roomsList.length}개 객실 로드)`);

  // Target a room for testing (e.g. 205)
  const targetRoom = roomsList.find(r => r.roomNo === '205') || roomsList[0];
  const targetRoomNo = targetRoom.roomNo;
  assert(!!targetRoom, `3. 대상 객실(${targetRoomNo}호) 초기 데이터 확인 (현재 상태: ${targetRoom?.cleaningStatus}, v${targetRoom?.version})`);

  // 3. Multi-Role Authentication
  const maidLogin = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ employeeNo: '1001' })
  });
  assert(maidLogin.ok && maidLogin.data?.token, 
    `4. 룸메이드 사번 인증 (/api/auth/login -> ${maidLogin.data?.user?.name} [${maidLogin.data?.user?.role}])`);

  const qmLogin = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ employeeNo: 'QM-2001' })
  });
  assert(qmLogin.ok && qmLogin.data?.token, 
    `5. QM 인스펙터 사번 인증 (/api/auth/login -> ${qmLogin.data?.user?.name} [${qmLogin.data?.user?.role}])`);

  const adminLogin = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ employeeNo: 'ADMIN-01' })
  });
  assert(adminLogin.ok && adminLogin.data?.token, 
    `6. 총괄 관리자 사번 인증 (/api/auth/login -> ${adminLogin.data?.user?.name} [${adminLogin.data?.user?.role}])`);

  // 4. Workflow Step 1: Admin assigns Maid (1001) to target room
  const curVer = targetRoom.version;
  const assignRes = await request(`/api/rooms/${targetRoomNo}/action`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${adminLogin.data.token}` },
    body: JSON.stringify({
      action: 'ASSIGN_ROOMMAID',
      expectedVersion: curVer,
      assigneeEmployeeNo: '1001',
      requestId: `req-assign-${Date.now()}`
    })
  });
  const roomAfterAssign = assignRes.data?.data || assignRes.data?.room;
  assert(assignRes.ok && roomAfterAssign && roomAfterAssign.roommaidEmployeeNo === '1001',
    `7. 관리자 ${targetRoomNo}호 룸메이드(김순자) 배정 (ASSIGN_ROOMMAID -> v${roomAfterAssign?.version})`);

  // 5. Workflow Step 2: Maid starts cleaning target room
  const startCleaning = await request(`/api/rooms/${targetRoomNo}/action`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${maidLogin.data.token}` },
    body: JSON.stringify({
      action: 'CLEANING_START',
      expectedVersion: roomAfterAssign?.version,
      requestId: `req-start-${Date.now()}`
    })
  });
  const roomCleaning = startCleaning.data?.data || startCleaning.data?.room;
  assert(startCleaning.ok && roomCleaning?.cleaningStatus === 'CLEANING', 
    `8. 룸메이드 ${targetRoomNo}호 정비 시작 (CLEANING_START -> CLEANING, v${roomCleaning?.version})`);

  // 6. Workflow Step 3: Maid completes cleaning target room
  const finishCleaning = await request(`/api/rooms/${targetRoomNo}/action`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${maidLogin.data.token}` },
    body: JSON.stringify({
      action: 'CLEANING_COMPLETE',
      expectedVersion: roomCleaning?.version,
      requestId: `req-finish-${Date.now()}`
    })
  });
  const roomCleaned = finishCleaning.data?.data || finishCleaning.data?.room;
  assert(finishCleaning.ok && roomCleaned?.cleaningStatus === 'QM_WAITING',
    `9. 룸메이드 ${targetRoomNo}호 정비 완료 (CLEANING_COMPLETE -> QM_WAITING, v${roomCleaned?.version})`);

  // 7. Workflow Step 4: Concurrency Control (OCC) - Conflicting Inspection Actions
  const vBeforeInspection = roomCleaned?.version;
  const [conflictReq1, conflictReq2] = await Promise.all([
    request(`/api/rooms/${targetRoomNo}/action`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${qmLogin.data.token}` },
      body: JSON.stringify({
        action: 'INSPECTION_PASS',
        expectedVersion: vBeforeInspection,
        requestId: `req-occ-pass-${Date.now()}`
      })
    }),
    request(`/api/rooms/${targetRoomNo}/action`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${qmLogin.data.token}` },
      body: JSON.stringify({
        action: 'INSPECTION_REWORK',
        expectedVersion: vBeforeInspection,
        requestId: `req-occ-rework-${Date.now()}`
      })
    })
  ]);

  const hasSuccess = conflictReq1.ok || conflictReq2.ok;
  const hasConflict = conflictReq1.status === 409 || conflictReq2.status === 409;
  assert(hasSuccess && hasConflict,
    `10. 동시 트랜잭션 충돌 방어 OCC 검증 (1건 성공: 200, 1건 충돌 차단: 409 Conflict)`);

  // 8. Houseman Order Creation & Auto Assignment Engine
  const newOrder = await request('/api/orders', {
    method: 'POST',
    headers: { Authorization: `Bearer ${maidLogin.data.token}` },
    body: JSON.stringify({
      roomNo: targetRoomNo,
      category: 'TOWEL',
      itemSummary: '대형 배스타월 4장',
      quantity: 4,
      important: true,
      note: `${targetRoomNo}호 고객 긴급 요청`
    })
  });
  const createdOrder = newOrder.data?.order || newOrder.data;
  assert(newOrder.ok && createdOrder?.orderId && createdOrder?.assignedEmployeeNo,
    `11. 하우스맨 오더 실시간 생성 및 자동 거리/부하 가중 배정 (배정자: ${createdOrder?.assignedName})`);

  // 9. Audit History Log API
  const historyRes = await request(`/api/rooms/${targetRoomNo}/events`);
  const events = historyRes.data?.events || historyRes.data || [];
  assert(historyRes.ok && Array.isArray(events) && events.length >= 3,
    `12. ${targetRoomNo}호 감사 로그 누적 트랜잭션 검증 (총 ${events.length}건 작업 기록)`);

  console.log('\n====================================================');
  console.log(`?? Live Server E2E Test Result: ${passed} Passed, ${failed} Failed`);
  console.log('====================================================');

  if (failed > 0) {
    process.exit(1);
  }
}

runE2ETests().catch(err => {
  console.error('Fatal Test Error:', err);
  process.exit(1);
});
