from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLOUD = ROOT / 'cloudrun' / 'index.js'


def fail(message):
    raise SystemExit(f'PATCH_ERROR: {message}')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


text = CLOUD.read_text(encoding='utf-8')

text = replace_once(
    text,
    "const NOVA_REALTIME_BUILD = 'phase1-v3.9-houseman-manual-assign';",
    "const NOVA_REALTIME_BUILD = 'phase1-v4.0-qm-realtime';",
    'Cloud Run build marker'
)

old = """    QM_ASSIGN: ['cleaningStatus', 'qmEmployeeNo'],
    CHANGE_ROOM_STATUS: [
"""
new = """    QM_ASSIGN: ['cleaningStatus', 'qmEmployeeNo'],
    QM_START: ['cleaningStatus', 'qmEmployeeNo'],
    QM_COMPLETE: ['cleaningStatus', 'qmEmployeeNo'],
    QM_REWORK: ['cleaningStatus', 'qmEmployeeNo'],
    CHANGE_ROOM_STATUS: [
"""
text = replace_once(text, old, new, 'QM action expected-state fields')

old = """  if (['CLEANING_START', 'CLEANING_COMPLETE'].includes(actionKey)) return;
"""
new = """  if (['CLEANING_START', 'CLEANING_COMPLETE', 'QM_START', 'QM_COMPLETE', 'QM_REWORK'].includes(actionKey)) return;
"""
text = replace_once(text, old, new, 'QM semantic concurrency guard')

old = """        !['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(action)
"""
new = """        !['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(action)
"""
text = replace_once(text, old, new, 'QM action whitelist')

anchor = """

      if (
        !canCleanRoom(
          user,
          room
        )
      ) {
"""
if text.count(anchor) != 1:
    fail(f'QM handler insertion anchor: expected 1 match, found {text.count(anchor)}')

handler = r'''

      if (['QM_START', 'QM_COMPLETE', 'QM_REWORK'].includes(action)) {
        if (String(user.role || '').toUpperCase() !== 'QM') {
          throw httpError(403, 'FORBIDDEN', 'QM 점검 처리 권한이 없습니다.');
        }

        if (String(room.qm_employee_no || '') !== String(user.employee_no || '')) {
          throw httpError(403, 'FORBIDDEN', '본인에게 배정된 객실만 점검할 수 있습니다.');
        }

        // QM 상태변경은 같은 객실 row-lock + 본인 배정 + 실제 현재상태로 직렬화한다.
        // 독립 필드의 version 증가 때문에 정상 점검이 막히지 않게 coarse version은 사용하지 않는다.
        assertRoomActionVersion_(action, expectedVersion, body.expectedState, room);

        const before = String(room.cleaning_status || '').trim().toUpperCase();
        const target = action === 'QM_START'
          ? 'QM_CHECKING'
          : (action === 'QM_COMPLETE' ? 'QM_COMPLETED' : 'REWORK');

        if (before === target) {
          const response = {
            ok: true,
            action,
            requestId,
            idempotent: true,
            room: roomDto(room),
            version: Number(room.version || 0),
            timing: { totalMs: Date.now() - startedAt }
          };
          await client.query(
            `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
            [requestId, JSON.stringify(response)]
          );
          await client.query('commit');
          return res.json(response);
        }

        const allowed = action === 'QM_START'
          ? new Set(['QM_WAITING', 'COMPLETED', 'QM_CHECKING'])
          // 전환 직후 이미 열린 체크리스트는 DB가 아직 QM_WAITING일 수 있어 1회 호환 허용.
          : new Set(['QM_CHECKING', 'QM_WAITING']);

        if (!allowed.has(before)) {
          throw httpError(
            409,
            'INVALID_STATE',
            `현재 ${before || '-'} 상태에서는 ${action === 'QM_START' ? 'QM 점검을 시작' : 'QM 점검을 완료'}할 수 없습니다.`
          );
        }

        const updated = await client.query(
          `update public.nova_rooms_current
              set cleaning_status=$4,
                  version=version+1,
                  updated_by=$5,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [businessDate, site, roomNo, target, user.employee_no]
        );
        const nextRoom = updated.rows[0];
        const detail = {
          source: 'NOVA_REALTIME',
          role: 'QM',
          qmEmployeeNo: String(user.employee_no || ''),
          qmName: String(user.name || ''),
          cleaningStatus: target
        };

        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            target,
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const response = {
          ok: true,
          action,
          requestId,
          room: roomDto(nextRoom),
          version: Number(nextRoom.version || 0),
          timing: { totalMs: Date.now() - startedAt }
        };
        await client.query(
          `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
          [requestId, JSON.stringify(response)]
        );
        await client.query('commit');
        return res.json(response);
      }
'''
text = text.replace(anchor, handler + anchor, 1)

CLOUD.write_text(text, encoding='utf-8')

subprocess.run(['node', '--check', str(CLOUD)], cwd=ROOT, check=True)
subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)

check = CLOUD.read_text(encoding='utf-8')
for needle in [
    "phase1-v4.0-qm-realtime",
    "'QM_START', 'QM_COMPLETE', 'QM_REWORK'",
    "if (['QM_START', 'QM_COMPLETE', 'QM_REWORK'].includes(action))",
    "set cleaning_status=$4",
    "본인에게 배정된 객실만 점검할 수 있습니다."
]:
    if needle not in check:
        fail(f'missing guard: {needle}')

print('QM_REALTIME_CLOUDRUN_V62_OK')
print('Changed: cloudrun/index.js only')
print('QM_START -> QM_CHECKING')
print('QM_COMPLETE -> QM_COMPLETED')
print('QM_REWORK -> REWORK')
print('Per-room row lock / QM ownership / idempotency preserved')
print('Syntax/scope: PASS')
