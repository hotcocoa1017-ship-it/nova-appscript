from pathlib import Path

client_path = Path('Client.html')
cloud_path = Path('cloudrun/index.js')

client = client_path.read_text(encoding='utf-8')
cloud = cloud_path.read_text(encoding='utf-8')

old_client_anchor = """  async function saveRoomActionRealtimeOrLegacy_(legacyMethod, payload) {\n"""
if old_client_anchor not in client:
    raise SystemExit('Client saveRoomActionRealtimeOrLegacy_ anchor not found')

helper = r'''  async function mirrorRealtimeClearAssignmentToSheet_(payload) { // (DB 배정초기화 성공 후 이력/Sheet 보조 미러)
    const safe = Object.assign({}, payload || {}, {
      action: 'CLEAR_ASSIGNMENT',
      expectedVersion: 0
    });
    delete safe.sheetExpectedVersion;
    const delays = [0, 700, 1800, 4000];
    let lastError = null;
    for (let index = 0; index < delays.length; index += 1) {
      if (delays[index]) await novaRealtimeSleep_(delays[index]);
      try {
        const mirrored = await callServer('updateRoomOperation', state.token, safe);
        if (!mirrored?.ok) throw new Error(mirrored?.message || '배정초기화 이력 동기화 실패');
        setSyncStatus(`${safe.roomNo}호 배정초기화 · 기존 이력 동기화 완료`);
        return mirrored;
      } catch (error) {
        lastError = error;
      }
    }
    console.error('[NOVA Realtime] 배정초기화 Sheet 미러 실패:', lastError);
    setSyncStatus(`${safe.roomNo}호 배정초기화 DB 완료 · 기존 이력 동기화 재확인 필요`);
    return null;
  }

'''
client = client.replace(old_client_anchor, helper + old_client_anchor, 1)

old_client_result = """    result.version = Number(result.version || result.room?.version || 0);\n    if (mappedAction === 'CHANGE_ROOM_STATUS') {\n"""
new_client_result = """    result.version = Number(result.version || result.room?.version || 0);\n    if (mappedAction === 'CLEAR_ASSIGNMENT' && result.eventDeferred === true) {\n      // DB 초기화는 이미 확정되었습니다. DB 이벤트 스키마가 구버전인 경우에만\n      // 기존 Sheet/업무이력을 사용자 응답 경로 밖에서 안전하게 보완합니다.\n      void mirrorRealtimeClearAssignmentToSheet_(legacySafe);\n    }\n    if (mappedAction === 'CHANGE_ROOM_STATUS') {\n"""
if old_client_result not in client:
    raise SystemExit('Client result anchor not found')
client = client.replace(old_client_result, new_client_result, 1)

old_cloud_event = r'''        await client.query(
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

        const responseRoom = {
'''
new_cloud_event = r'''        let eventDeferred = false;
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

        const responseRoom = {
'''
if old_cloud_event not in cloud:
    raise SystemExit('Cloud CLEAR_ASSIGNMENT event block not found')
cloud = cloud.replace(old_cloud_event, new_cloud_event, 1)

old_cloud_response = r'''          room: responseRoom,
          version: Number(nextRoom.version || 0),
          timing: { totalMs: Date.now() - startedAt }
        };
'''
new_cloud_response = r'''          room: responseRoom,
          version: Number(nextRoom.version || 0),
          eventDeferred,
          timing: { totalMs: Date.now() - startedAt }
        };
'''
# Replace only the response immediately following CLEAR_ASSIGNMENT by locating after the new block.
pos = cloud.find(new_cloud_event)
if pos < 0:
    raise SystemExit('Cloud patched event block missing')
resp_pos = cloud.find(old_cloud_response, pos)
if resp_pos < 0:
    raise SystemExit('Cloud CLEAR_ASSIGNMENT response block not found')
cloud = cloud[:resp_pos] + cloud[resp_pos:].replace(old_cloud_response, new_cloud_response, 1)

client_path.write_text(client, encoding='utf-8')
cloud_path.write_text(cloud, encoding='utf-8')
print('CLEAR_ASSIGNMENT DB event compatibility fallback patch applied')
