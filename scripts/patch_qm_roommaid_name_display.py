from pathlib import Path
import sys

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
marker = 'QM 점검대상 정비자 이름 보존 v1'

if marker in text:
    print('QM roommaid display-name patch already applied.')
    sys.exit(0)

helper_anchor = "  function novaRealtimeHandleBroadcast_(payload) {\n"
if helper_anchor not in text:
    print('ERROR: Realtime broadcast anchor not found.', file=sys.stderr)
    sys.exit(50)

helper = r'''  function preserveQmMobileRoommaidNames_(previousRoom, mergedRoom) { // (QM 점검대상 정비자 이름 보존 v1)
    if (String(state.mobile.data?.role || '').trim().toUpperCase() !== 'QM' || !previousRoom || !mergedRoom) return mergedRoom;
    const next = Object.assign({}, mergedRoom);
    const previousPrimaryNo = String(previousRoom.roommaidEmployeeNo || '').trim();
    const nextPrimaryNo = String(next.roommaidEmployeeNo || '').trim();
    const previousSecondaryNo = String(previousRoom.secondaryRoommaidEmployeeNo || '').trim();
    const nextSecondaryNo = String(next.secondaryRoommaidEmployeeNo || '').trim();

    // Realtime DB에는 사번만 있으므로 같은 배정자라면 Sheet 스냅샷의 표시명을 유지합니다.
    // 배정 사번이 실제로 변경된 경우에는 기존 이름을 절대 이월하지 않습니다.
    if (nextPrimaryNo && previousPrimaryNo === nextPrimaryNo && String(previousRoom.roommaidName || '').trim()) {
      next.roommaidName = String(previousRoom.roommaidName || '').trim();
    }
    if (nextSecondaryNo && previousSecondaryNo === nextSecondaryNo && String(previousRoom.secondaryRoommaidName || '').trim()) {
      next.secondaryRoommaidName = String(previousRoom.secondaryRoommaidName || '').trim();
    }
    return next;
  }

'''
text = text.replace(helper_anchor, helper + helper_anchor, 1)

replacements = [
    (
        "          if (legacyRoom) return novaRealtimeMergeRoom_(legacyRoom, realtimeRoom);\n",
        "          if (legacyRoom) return preserveQmMobileRoommaidNames_(legacyRoom, novaRealtimeMergeRoom_(legacyRoom, realtimeRoom));\n",
        'QM DB hydration'
    ),
    (
        "      mobileRooms[mobileIndex] = novaRealtimeMergeRoom_(mobileRooms[mobileIndex], room);\n",
        "      const previousMobileRoom = mobileRooms[mobileIndex];\n      mobileRooms[mobileIndex] = preserveQmMobileRoommaidNames_(previousMobileRoom, novaRealtimeMergeRoom_(previousMobileRoom, room));\n",
        'QM/mobile broadcast'
    ),
    (
        "    rooms[index] = novaRealtimeMergeRoom_(rooms[index], mapped);\n",
        "    const previousRoom = rooms[index];\n    rooms[index] = preserveQmMobileRoommaidNames_(previousRoom, novaRealtimeMergeRoom_(previousRoom, mapped));\n",
        'QM action response'
    )
]

for old, new, label in replacements:
    count = text.count(old)
    if count != 1:
        print(f'ERROR: Expected exactly 1 {label} anchor, found {count}.', file=sys.stderr)
        sys.exit(51)
    text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
print('Applied QM roommaid display-name preservation patch to Client.html.')
