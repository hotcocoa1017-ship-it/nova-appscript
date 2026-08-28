from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
old = """    const rawAction = String(safe.action || '').trim().toUpperCase();
    const mappedAction = rawAction === 'START' ? 'CLEANING_START'
      : rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'
      : rawAction;
"""
new = """    const rawAction = String(safe.action || '').trim().toUpperCase();
    // START/COMPLETE 명칭은 룸메이드 모바일과 하우스맨 오더가 함께 사용한다.
    // 객실 Realtime 액션으로의 변환은 룸메이드 모바일 작업에만 적용해야 한다.
    // 하우스맨 START/COMPLETE를 CLEANING_*으로 바꾸면 /v1/rooms/.../action으로 잘못 전송되어 404가 발생한다.
    const roommaidMobileOperation = legacyMethod === 'updateMobileRoomOperation';
    const mappedAction = roommaidMobileOperation && rawAction === 'START' ? 'CLEANING_START'
      : roommaidMobileOperation && rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'
      : rawAction;
"""
if old not in text:
    raise SystemExit('target block not found')
text = text.replace(old, new, 1)

# Guards: houseman raw actions must remain legacy, while roommaid mapping and QM realtime actions stay present.
assert "const roommaidMobileOperation = legacyMethod === 'updateMobileRoomOperation';" in text
assert "roommaidMobileOperation && rawAction === 'START' ? 'CLEANING_START'" in text
assert "roommaidMobileOperation && rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'" in text
assert "'QM_START', 'QM_COMPLETE', 'QM_REWORK'" in text
assert "const housemanFastPath = method === 'updateHousemanOrder'" in text

path.write_text(text, encoding='utf-8')
print('HOUSEMAN_ACTION_ROUTE_FIX_V85_OK')
