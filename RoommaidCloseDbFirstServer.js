/**
 * 룸메이드 마감일지 PostgreSQL 우선 history 조회 브리지.
 * 마감 완료(native_complete=true)는 확정 DB history/snapshot을 사용하고,
 * 마감 전에도 daily-close DB source 준비조건을 통과하면 DB history를 사용합니다.
 * 그 외 과거·미완전 업무일자는 기존 Sheet TextFinder 경로를 유지합니다.
 */
function novaRoommaidCloseHistoryDbFirstEnabled_() { // ROOMMAID_CLOSE_HISTORY_DB_FIRST_V1
  const props = PropertiesService.getScriptProperties();
  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;
  return String(props.getProperty('NOVA_ROOMMAID_CLOSE_HISTORY_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';
}

function novaRoommaidCloseHistoryDbRead_(token, businessDate, site) { // ROOMMAID_CLOSE_HISTORY_DB_FIRST_V1
  return novaRealtimeUserRpc_(token, 'nova_roommaid_close_history_v1', {
    p_business_date: String(businessDate || '').trim(),
    p_site: String(site || '').trim()
  });
}

function readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, site) { // ROOMMAID_CLOSE_HISTORY_DB_FIRST_V2
  if (!token || !novaRoommaidCloseHistoryDbFirstEnabled_()) {
    return Object.assign({}, readRoommaidCloseHistoryBundleFast_(businessDate, site), {
      dbFirst: false,
      nativeComplete: false,
      sourceReady: false,
      stateVersion: 0,
      dbSaved: null
    });
  }

  try {
    // 1) 이미 공식 마감된 DB-native 날짜는 확정 history + DB close snapshot을 사용합니다.
    const result = novaRoommaidCloseHistoryDbRead_(token, businessDate, site);
    if (result && result.nativeComplete === true) {
      const dbSaved = readDailyCloseDbSnapshots_(token, businessDate, businessDate, site)[0] || null;
      return {
        historyRows: Array.isArray(result.items) ? result.items : [],
        saved: dbSaved,
        dbSaved,
        dbFirst: true,
        nativeComplete: true,
        sourceReady: true,
        stateVersion: Number(result.stateVersion || 0)
      };
    }

    // 2) 마감 전이라도 객실업로드/정비/QM/운영설정 정합성이 모두 확인되면
    // daily-close source RPC의 history를 원본으로 사용해 Sheet TextFinder를 건너뜁니다.
    if (typeof tryNovaDailyCloseDbSource_ === 'function') {
      const liveSource = tryNovaDailyCloseDbSource_(token, businessDate, site);
      if (liveSource && liveSource.ready === true) {
        return {
          historyRows: Array.isArray(liveSource.historyRows) ? liveSource.historyRows : [],
          saved: null,
          dbSaved: null,
          dbFirst: true,
          nativeComplete: false,
          sourceReady: true,
          stateVersion: Number(result && result.stateVersion || 0)
        };
      }
    }
  } catch (error) {
    console.warn('[NOVA ROOMMAID CLOSE DB history fallback]', error && error.message ? error.message : error);
  }

  return Object.assign({}, readRoommaidCloseHistoryBundleFast_(businessDate, site), {
    dbFirst: false,
    nativeComplete: false,
    sourceReady: false,
    stateVersion: 0,
    dbSaved: null
  });
}
