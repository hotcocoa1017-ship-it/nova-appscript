from pathlib import Path

path = Path('cloudrun/index.js')
text = path.read_text(encoding='utf-8')

reset_start = text.find("      if (action === 'CLEANING_RESET') {")
clear_start = text.find("      if (action === 'CLEAR_ASSIGNMENT') {", reset_start + 1)
next_start = text.find("      if (action === 'UPDATE_OPERATION_FLAGS') {", clear_start + 1)
if min(reset_start, clear_start, next_start) < 0:
    raise SystemExit('Expected action branch markers not found')

reset_block = text[reset_start:clear_start]
clear_block = text[clear_start:next_start]

compat_block = r'''        let eventDeferred = false;
        // 일부 기존 DB에는 nova_room_events.action 허용값이 구버전으로 남아 있을 수 있습니다.
        // 객실 배정초기화 자체는 먼저 확정하고, CLEAR_ASSIGNMENT 이벤트 값만 거절되는 경우에는
        // SAVEPOINT로 이벤트 INSERT만 되돌린 뒤 Client가 기존 Sheet/업무이력을 보조 미러합니다.
        await client.query('savepoint nova_clear_assignment_event');
        try {
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
              previousCleaningStatus,
              'WAITING',
              user.employee_no,
              nextRoom.version,
              JSON.stringify(detail)
            ]
          );
        } catch (eventError) {
          const pgCode = String(eventError?.code || '');
          await client.query('rollback to savepoint nova_clear_assignment_event');
          if (!['23514', '22P02'].includes(pgCode)) throw eventError;
          eventDeferred = true;
          console.warn('[NOVA Realtime] CLEAR_ASSIGNMENT event deferred', {
            code: pgCode,
            constraint: String(eventError?.constraint || '')
          });
        }
'''

plain_block = r'''        await client.query(
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
            previousCleaningStatus,
            'WAITING',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );
'''

if compat_block not in reset_block:
    raise SystemExit('Misplaced compatibility block not found in CLEANING_RESET')
reset_block = reset_block.replace(compat_block, plain_block, 1)

if compat_block in clear_block:
    raise SystemExit('Compatibility block already exists in CLEAR_ASSIGNMENT')
if plain_block not in clear_block:
    raise SystemExit('Plain event insert not found in CLEAR_ASSIGNMENT')
clear_block = clear_block.replace(plain_block, compat_block, 1)

if 'eventDeferred,' not in clear_block:
    raise SystemExit('CLEAR_ASSIGNMENT response does not expose eventDeferred')
if 'eventDeferred,' in reset_block:
    raise SystemExit('CLEANING_RESET response unexpectedly exposes eventDeferred')

text = text[:reset_start] + reset_block + clear_block + text[next_start:]
path.write_text(text, encoding='utf-8')
print('CLEAR_ASSIGNMENT compatibility fallback moved to correct branch')
