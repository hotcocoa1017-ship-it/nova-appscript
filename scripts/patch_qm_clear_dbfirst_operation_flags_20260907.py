from pathlib import Path
import sys

CLIENT = Path('Client.html')
REALTIME = Path('RealtimeDailySync.js')
MARKER_QM = 'QM_CLEAR_DB_FIRST_V2'
MARKER_FLAGS = 'ROOM_OPERATION_FLAGS_FORWARD_SYNC_V2'
MARKER_MIRROR = 'QM_CLEAR_EVENT_MIRROR_V2'


def fail(message):
    print(f'ERROR: {message}', file=sys.stderr)
    sys.exit(91)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        if count == 0 and new in text:
            return text
        fail(f'{label}: expected exactly 1 anchor, found {count}')
    return text.replace(old, new, 1)


def patch_client():
    text = CLIENT.read_text(encoding='utf-8')

    helper_anchor = "  async function saveRoomActionRealtimeOrLegacy_(legacyMethod, payload) {\n"
    helper = r'''  // QM_CLEAR_DB_FIRST_V2
  // 관리자 QM 배정 초기화는 DB를 먼저 확정합니다. 네트워크 결과가 불명확할 때는
  // 동일 requestId로만 재확인하며 Sheet-first 경로를 병행하지 않습니다.
  async function novaQmClearDbFirst_(payload) {
    const safe = Object.assign({}, payload || {});
    const requestId = String(safe.requestId || novaRealtimeRequestId_('QM_CLEAR', safe.roomNo || '')).trim();
    const businessDate = String(safe.businessDate || state.indicator.businessDate || state.bootstrap?.app?.businessDate || '').trim();
    const site = String(safe.site || state.indicator.site || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!businessDate || !site || !roomNo) throw new Error('QM 배정 초기화에 업무일자·사업장·객실번호가 필요합니다.');

    let auth;
    try {
      auth = await novaQmDraftAuthBundle_();
    } catch (error) {
      // 아직 DB 요청을 전송하지 않은 단계이므로 기존 경로 fallback이 안전합니다.
      console.warn('[NOVA QM] QM_CLEAR DB 인증 준비 실패 · 기존 경로 사용:', error?.message || error);
      return { ok: false, legacyFallback: true, reason: 'AUTH_PREP_FAILED' };
    }

    const body = {
      p_business_date: businessDate,
      p_site: site,
      p_room_no: roomNo,
      p_request_id: requestId
    };

    const send = async attempt => {
      const endpoint = `${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_qm_clear_v1`;
      let response;
      try {
        response = await novaRealtimeBoundedFetch_(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'apikey': String(auth.publishableKey || ''),
            'Authorization': `Bearer ${String(auth.token || '')}`
          },
          body: JSON.stringify(body)
        }, 5500);
      } catch (networkError) {
        if (attempt < 2) {
          await novaRealtimeSleep_([160, 420, 900][attempt] || 900);
          return send(attempt + 1);
        }
        const error = new Error('QM 배정 초기화 결과를 확인하지 못했습니다. 객실 상태를 다시 확인해 주세요.');
        error.code = 'QM_CLEAR_DB_RESULT_UNKNOWN';
        error.cause = networkError;
        throw error;
      }

      let data = {};
      try { data = await response.json(); } catch (ignore) {}
      if (response.ok && data?.ok) return data;

      const code = String(data?.code || '').trim().toUpperCase();
      if (response.status === 401 && attempt < 2) {
        novaRealtime_.qmDraftAuthBundle = null;
        auth = await novaQmDraftAuthBundle_();
        await novaRealtimeSleep_(140);
        return send(attempt + 1);
      }
      if ((response.status === 429 || response.status >= 500) && attempt < 2) {
        await novaRealtimeSleep_([160, 420, 900][attempt] || 900);
        return send(attempt + 1);
      }
      if (response.status === 404 || ['PGRST202', 'PGRST205'].includes(code)) {
        // RPC 자체가 없는 경우에는 DB 변경이 없으므로 기존 Sheet 경로가 안전합니다.
        return { ok: false, legacyFallback: true, reason: 'RPC_MISSING' };
      }

      const error = new Error(data?.message || data?.details || data?.hint || `QM 배정 초기화 DB 오류 (${response.status})`);
      error.status = Number(response.status || 0);
      error.code = data?.code || '';
      throw error;
    };

    return send(0);
  }

'''
    if MARKER_QM not in text:
        text = replace_once(text, helper_anchor, helper + helper_anchor, 'insert QM_CLEAR DB-first helper')

    old_actions = "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)\n"
    new_actions = "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_CLEAR', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)\n"
    text = replace_once(text, old_actions, new_actions, 'route QM_CLEAR as Realtime action')

    intercept_anchor = "    const operationalStatusReworkDirect = mappedAction === 'UPDATE_ROOM_OPERATION_STATUS'\n"
    intercept = r'''    if (mappedAction === 'QM_CLEAR') { // QM_CLEAR_DB_FIRST_V2
      const directResult = await novaQmClearDbFirst_(safe);
      if (directResult?.legacyFallback) {
        return callServer(legacyMethod, state.token, legacySafe);
      }
      directResult.version = Number(directResult.version || directResult.room?.version || 0);
      directResult.message = directResult.message || 'QM 배정을 초기화했습니다.';
      return directResult;
    }

'''
    if text.count(intercept) == 0:
        text = replace_once(text, intercept_anchor, intercept + intercept_anchor, 'insert QM_CLEAR direct RPC branch')

    CLIENT.write_text(text, encoding='utf-8')


def patch_realtime():
    text = REALTIME.read_text(encoding='utf-8')

    mirror_anchor = "      if (action === 'UPDATE_OPERATION_FLAGS') {\n"
    mirror = r'''      if (action === 'QM_CLEAR') { // QM_CLEAR_EVENT_MIRROR_V2
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const previousQmEmployeeNo = String(eventDetail.previousQmEmployeeNo || qmNo || '').trim();
        const previousCleaningStatus = String(eventDetail.previousCleaningStatus || beforeStatus || 'QM_WAITING').trim().toUpperCase();
        const mirroredCleaningType = String(eventDetail.cleaningType || cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();
        const mirroredAssignmentType = String(eventDetail.assignmentType || assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();
        const mirroredPrimaryNo = String(eventDetail.primaryEmployeeNo || roommaidNo || '').trim();
        const mirroredSecondaryNo = String(eventDetail.secondaryEmployeeNo || secondaryRoommaidNo || '').trim();

        // 같은 이벤트 배치에 QM_ASSIGN -> QM_CLEAR가 연속으로 있어도 마지막 이벤트가 이기도록
        // 기존 roomUpdates 병합 큐를 사용합니다. 직접 Sheet 쓰기는 앞선 큐가 뒤에서 덮을 수 있습니다.
        roomUpdates.push({
          rowNumber: rowInfo.rowNumber,
          cleaningStatus: 'COMPLETED',
          qmEmployeeNo: '',
          version,
          updatedAt: nowText_()
        });
        rowInfo.data['QM사번'] = '';
        rowInfo.data['청소상태'] = 'COMPLETED';
        rowInfo.data['마지막변경버전'] = version;

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.QM,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: previousQmEmployeeNo,
          status: 'QM_CLEAR',
          detail: {
            requestId,
            realtime: true,
            action: 'QM_CLEAR',
            role: String(eventDetail.role || 'ORDER').trim().toUpperCase(),
            previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            previousCleaningStatus,
            cleaningStatus: 'COMPLETED',
            cleaningType: mirroredCleaningType,
            assignmentType: mirroredAssignmentType,
            primaryEmployeeNo: mirroredPrimaryNo,
            secondaryEmployeeNo: mirroredSecondaryNo,
            previousQmEmployeeNo,
            qmEmployeeNo: '',
            preassigned: Object.prototype.hasOwnProperty.call(eventDetail, 'preassigned')
              ? eventDetail.preassigned === true
              : normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
            vip: Object.prototype.hasOwnProperty.call(eventDetail, 'vip')
              ? eventDetail.vip === true
              : normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
            importantRoom: Object.prototype.hasOwnProperty.call(eventDetail, 'importantRoom')
              ? eventDetail.importantRoom === true
              : normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
            dbRoomVersion: Number(event.roomVersion || 0),
            dbEventTime: String(event.eventTime || '')
          },
          registeredBy: employeeNo,
          version
        });

        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

'''
    if MARKER_MIRROR not in text:
        text = replace_once(text, mirror_anchor, mirror + mirror_anchor, 'insert QM_CLEAR event mirror')

    flags_anchor = "      qmEmployeeNo: String(row[map['QM사번']] || '').trim(),\n"
    flags = "      qmEmployeeNo: String(row[map['QM사번']] || '').trim(),\n      // ROOM_OPERATION_FLAGS_FORWARD_SYNC_V2 · DB-first 운영표시가 5분 정방향 동기화에서 유실되지 않게 명시합니다.\n      preassigned: map['선배정여부'] !== undefined && normalizeYesNo_(row[map['선배정여부']]) === 'Y',\n      vip: map['VIP여부'] !== undefined && normalizeYesNo_(row[map['VIP여부']]) === 'Y',\n      importantRoom: map['중요객실여부'] !== undefined && normalizeYesNo_(row[map['중요객실여부']]) === 'Y',\n"
    if MARKER_FLAGS not in text:
        text = replace_once(text, flags_anchor, flags, 'preserve operation flags in forward sync payload')

    REALTIME.write_text(text, encoding='utf-8')


def main():
    patch_client()
    patch_realtime()
    print('QM_CLEAR DB-first + operation flags forward-sync patch applied.')


if __name__ == '__main__':
    main()
