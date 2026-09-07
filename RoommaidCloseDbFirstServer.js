/**
 * 룸메이드 마감일지 PostgreSQL 우선 history 조회 브리지.
 * reporting native_complete=true인 업무일자/사업장만 DB history가 원본이며,
 * 나머지는 기존 Sheet TextFinder 경로를 그대로 사용합니다.
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

function readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, site) { // ROOMMAID_CLOSE_HISTORY_DB_FIRST_V1
  if (!token || !novaRoommaidCloseHistoryDbFirstEnabled_()) {
    return Object.assign({}, readRoommaidCloseHistoryBundleFast_(businessDate, site), {
      dbFirst: false,
      nativeComplete: false,
      stateVersion: 0,
      dbSaved: null
    });
  }

  try {
    const result = novaRoommaidCloseHistoryDbRead_(token, businessDate, site);
    if (result && result.nativeComplete === true) {
      const dbSaved = readDailyCloseDbSnapshots_(token, businessDate, businessDate, site)[0] || null;
      return {
        historyRows: Array.isArray(result.items) ? result.items : [],
        saved: dbSaved,
        dbSaved,
        dbFirst: true,
        nativeComplete: true,
        stateVersion: Number(result.stateVersion || 0)
      };
    }
  } catch (error) {
    console.warn('[NOVA ROOMMAID CLOSE DB history fallback]', error && error.message ? error.message : error);
  }

  return Object.assign({}, readRoommaidCloseHistoryBundleFast_(businessDate, site), {
    dbFirst: false,
    nativeComplete: false,
    stateVersion: 0,
    dbSaved: null
  });
}
