from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')

old = """    if (method === 'updateMobileRoomOperation') {
      const room = (state.mobile.data?.rooms || []).find(item => item.roomNo === safePayload.roomNo);
      if (!safePayload.expectedVersion) safePayload.expectedVersion = Number(room?.version || 0);
      if (!safePayload.rowNumber) safePayload.rowNumber = Number(room?.rowNumber || 0);
      if (!Object.prototype.hasOwnProperty.call(safePayload, 'qmEmployeeNo')) {
        safePayload.qmEmployeeNo = String(room?.qmEmployeeNo || '');
      }
    }
"""

new = """    if (method === 'updateMobileRoomOperation') {
      const room = (state.mobile.data?.rooms || []).find(item => item.roomNo === safePayload.roomNo);
      const mobileRoomAction = String(safePayload.action || '').trim().toUpperCase();
      const roommaidCleaningAction = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase() === 'ROOMMAID'
        && ['START', 'COMPLETE'].includes(mobileRoomAction);
      // 룸메이드 청소시작/완료는 서버가 실제 배정자와 현재 청소상태를 잠금 상태에서 다시 검증한다.
      // DB 이벤트 미러/정방향 동기화 사이에 version 값만 달라지는 경우가 있으므로
      // 이 두 작업은 stale version 때문에 정상 작업이 거절되지 않도록 상태·권한 검증을 원본으로 사용한다.
      if (roommaidCleaningAction) safePayload.expectedVersion = 0;
      else if (!safePayload.expectedVersion) safePayload.expectedVersion = Number(room?.version || 0);
      if (!safePayload.rowNumber) safePayload.rowNumber = Number(room?.rowNumber || 0);
      if (!Object.prototype.hasOwnProperty.call(safePayload, 'qmEmployeeNo')) {
        safePayload.qmEmployeeNo = String(room?.qmEmployeeNo || '');
      }
    }
"""

if 'const roommaidCleaningAction =' in text:
    print('Roommaid cleaning version guard already applied')
elif old not in text:
    raise SystemExit('Expected mobile room action version block not found')
else:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')
    print('Applied roommaid cleaning START/COMPLETE version guard')
