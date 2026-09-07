from pathlib import Path

MARKER = 'OPERATION_STATUS_DB_FIRST_V2'


def patch_server():
    path = Path('RoomOperationalStatusFix.js')
    text = path.read_text(encoding='utf-8')
    if MARKER in text:
        return

    anchor = """    const hasExpectedStatus = Object.prototype.hasOwnProperty.call(safe, 'expectedOperationalStatus');
    const rawExpectedStatus = String(safe.expectedOperationalStatus || '').trim();
    const expectedStatus = normalizeIndicatorRoomOperationalStatus_(rawExpectedStatus);
    if (rawExpectedStatus && !expectedStatus) throw new Error('현재 객실 조치상태를 확인하지 못했습니다.');

    ensureIndicatorRoomOperationalStatusHeader_();
"""
    replacement = """    const hasExpectedStatus = Object.prototype.hasOwnProperty.call(safe, 'expectedOperationalStatus');
    const rawExpectedStatus = String(safe.expectedOperationalStatus || '').trim();
    const expectedStatus = normalizeIndicatorRoomOperationalStatus_(rawExpectedStatus);
    if (rawExpectedStatus && !expectedStatus) throw new Error('현재 객실 조치상태를 확인하지 못했습니다.');

    // PostgreSQL이 원본인 동안에는 Sheet를 먼저 수정하지 않습니다. // OPERATION_STATUS_DB_FIRST_V2
    // 기존 Cloud Run 객실 action API가 권한·row lock·상태검증·이벤트 생성을 담당하고,
    // Sheets/업무이력은 RealtimeDailySync의 DB -> Sheet 이벤트 미러가 후행 반영합니다.
    if (typeof novaMobileRealtimeEnabled_ === 'function' && novaMobileRealtimeEnabled_()) {
      if (!requestedSite) throw new Error('사업장을 선택한 뒤 다시 처리하세요.');
      if (typeof novaMobileRealtimeActionFetch_ !== 'function') throw new Error('Realtime 객실 작업 기능을 찾을 수 없습니다.');

      const requestId = String(safe.requestId || '').trim() || `OPSTATUS:${Utilities.getUuid()}`;
      const dbPayload = {
        businessDate,
        site: requestedSite,
        action: 'UPDATE_ROOM_OPERATION_STATUS',
        operationalStatus: requestedStatus,
        requestId,
        expectedVersion: 0,
        expectedState: {
          operationalStatus: hasExpectedStatus ? expectedStatus : ''
        }
      };
      const dbResult = novaMobileRealtimeActionFetch_(token, roomNo, dbPayload);
      if (!dbResult || !dbResult.ok) {
        const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || `Realtime API 오류 (${dbResult && dbResult.__httpStatus || '-'})`));
        error.code = String(dbResult && dbResult.code || 'OPERATION_STATUS_DB_WRITE_FAILED');
        throw error;
      }

      const dbRoom = dbResult.room && typeof dbResult.room === 'object' ? dbResult.room : {};
      const dbVersion = Number(dbResult.version || dbRoom.version || 0);
      const finishedMs = Date.now();
      return {
        ok: true,
        dbFirst: true,
        alreadySet: Boolean(dbResult.idempotent || dbResult.alreadySet),
        version: dbVersion,
        requestId: String(dbResult.requestId || requestId),
        room: {
          rowNumber: Number(safe.rowNumber || 0),
          businessDate: String(dbRoom.businessDate || businessDate),
          site: String(dbRoom.site || requestedSite),
          roomNo: String(dbRoom.roomNo || roomNo),
          roomStatus: String(dbRoom.roomStatus || ''),
          cleaningStatus: String(dbRoom.cleaningStatus || ''),
          operationalStatus: Object.prototype.hasOwnProperty.call(dbRoom, 'operationalStatus')
            ? String(dbRoom.operationalStatus || '')
            : requestedStatus,
          updatedAt: String(dbRoom.updatedAt || ''),
          version: dbVersion
        },
        mirrorPending: true,
        timing: {
          safeOperationalStatus: true,
          dbFirst: true,
          durableWriteVerified: true,
          totalMs: Math.max(0, finishedMs - startedMs)
        }
      };
    }

    ensureIndicatorRoomOperationalStatusHeader_();
"""
    if anchor not in text:
        raise SystemExit('server anchor not found')
    text = text.replace(anchor, replacement, 1)
    path.write_text(text, encoding='utf-8')


def patch_client():
    path = Path('Client.html')
    text = path.read_text(encoding='utf-8')
    marker = 'OPERATION_STATUS_DB_FIRST_V2_CLIENT'
    if marker in text:
        return

    # The special operational-status paths already call updateRoomOperationalStatusSafe.
    # Remove only the now-obsolete follow-up Sheet->DB JIT calls immediately following those calls.
    old1 = """      void callServer('syncNovaRealtimeRoomForAction', state.token, {
        businessDate: safe.businessDate,
        site: safe.site,
        roomNo: safe.roomNo,
        action: 'UPDATE_ROOM_OPERATION_STATUS'
      }).catch(syncError => {
        console.warn('[NOVA Realtime] 재정비 객실조치 DB 단건 동기화는 정기 동기화로 넘깁니다.', syncError);
      });
      return Object.assign({}, directResult, { reworkOperationalSafePath: true });
"""
    new1 = """      // updateRoomOperationalStatusSafe 자체가 DB-first이므로 Sheet->DB JIT는 호출하지 않습니다. // OPERATION_STATUS_DB_FIRST_V2_CLIENT
      return Object.assign({}, directResult, { reworkOperationalSafePath: true, dbFirst: directResult.dbFirst === true });
"""
    if old1 not in text:
        raise SystemExit('client rework JIT anchor not found')
    text = text.replace(old1, new1, 1)

    old2 = """      void callServer('syncNovaRealtimeRoomForAction', state.token, {
        businessDate: safe.businessDate,
        site: safe.site,
        roomNo: safe.roomNo,
        action: 'UPDATE_ROOM_OPERATION_STATUS'
      }).catch(syncError => {
        console.warn('[NOVA Realtime] 객실조치 완료 후 DB 단건 재동기화는 정기 동기화로 넘깁니다.', syncError);
      });
      return Object.assign({}, directResult, { realtimeDirectSafePath: true });
"""
    new2 = """      // updateRoomOperationalStatusSafe 자체가 DB-first이므로 Sheet->DB JIT는 호출하지 않습니다. // OPERATION_STATUS_DB_FIRST_V2_CLIENT
      return Object.assign({}, directResult, { realtimeDirectSafePath: true, dbFirst: directResult.dbFirst === true });
"""
    if old2 not in text:
        raise SystemExit('client clear JIT anchor not found')
    text = text.replace(old2, new2, 1)

    # One fallback block for the same clear operation can exist after a direct API conflict.
    old3 = """        void callServer('syncNovaRealtimeRoomForAction', state.token, {
          businessDate: safe.businessDate,
          site: safe.site,
          roomNo: safe.roomNo,
          action: 'UPDATE_ROOM_OPERATION_STATUS'
        }).catch(syncError => {
          console.warn('[NOVA Realtime] 객실조치 완료 fallback 후 DB 단건 재동기화는 정기 동기화로 넘깁니다.', syncError);
        });
        return Object.assign({}, fallbackResult, { realtimeDirectFallback: true });
"""
    new3 = """        // fallback도 updateRoomOperationalStatusSafe DB-first 경로를 사용합니다. // OPERATION_STATUS_DB_FIRST_V2_CLIENT
        return Object.assign({}, fallbackResult, { realtimeDirectFallback: true, dbFirst: fallbackResult.dbFirst === true });
"""
    if old3 in text:
        text = text.replace(old3, new3, 1)

    path.write_text(text, encoding='utf-8')


patch_server()
patch_client()
print('patched operational status DB-first v2')
