/** NOVA_ROOMMAID_REPORTING_DB_FIRST_V2 · NOVA_ROOMMAID_REPORTING_DB_FIRST_V5 · ROOMMAID_CLOSE_SINGLE_BUNDLE_V5 */
function readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, site) {
  const dateText = normalizeBusinessDate_(businessDate);
  const siteText = String(site || '').trim();
  const db = novaDbFirstRpc_(token, 'nova_roommaid_close_history_v1', {
    p_business_date: dateText,
    p_site: siteText
  }, { readOnly: true, allowLegacyFallback: true });

  if (db && db.legacyFallback) {
    const fast = readRoommaidCloseHistoryBundleFast_(dateText, siteText);
    return Object.assign({}, fast, {
      currentRows: [],
      dbFirst: false,
      nativeComplete: false,
      readPath: String(fast && fast.readPath || 'SHEET_FALLBACK')
    });
  }

  if (!db || db.nativeComplete !== true) {
    const fast = readRoommaidCloseHistoryBundleFast_(dateText, siteText);
    return Object.assign({}, fast, {
      currentRows: [],
      dbFirst: false,
      nativeComplete: false,
      readPath: String(fast && fast.readPath || 'SHEET_INCOMPLETE_FALLBACK'),
      cacheComplete: Boolean(db && db.cacheComplete),
      cacheRows: Number(db && db.cacheRows || 0)
    });
  }

  const currentRows = roommaidCloseCurrentRowsFromDbBundle_(db, dateText, siteText);
  return {
    historyRows: Array.isArray(db.items) ? db.items : [],
    currentRows,
    saved: db.saved ? novaDailyCloseDbSummary_(db.saved) : null,
    dbFirst: true,
    nativeComplete: true,
    stateVersion: Number(db.stateVersion || 0),
    liveNativeReady: Boolean(db.liveNativeReady),
    cacheComplete: Boolean(db.cacheComplete),
    cacheRows: Number(db.cacheRows || 0),
    readPath: currentRows.length ? 'DB_NATIVE_SINGLE_BUNDLE_V5' : 'DB_NATIVE_BUNDLE_V4'
  };
}

function roommaidCloseCurrentRowsFromDbBundle_(db, businessDate, site) { // ROOMMAID_CLOSE_SINGLE_BUNDLE_V5
  const rows = db && Array.isArray(db.currentRows) ? db.currentRows : [];
  if (!rows.length) return [];
  const schema = db && Array.isArray(db.currentRowSchema) ? db.currentRowSchema : [];
  const index = {};
  schema.forEach((name, position) => { index[String(name || '').trim()] = position; });
  const at = (row, name, fallback) => {
    const position = index[name];
    return Number.isInteger(position) && Array.isArray(row) && position < row.length
      ? row[position]
      : fallback;
  };
  const seen = new Set();
  return rows.map(raw => {
    const roomNo = String(at(raw, 'roomNo', '') || '').trim();
    if (!roomNo) return null;
    const key = `${site}|${roomNo}`;
    if (seen.has(key)) return null;
    seen.add(key);
    return {
      '업무일자': businessDate,
      '객실번호': roomNo,
      '사업장': site,
      '동': String(at(raw, 'building', '') || ''),
      '객실상태': String(at(raw, 'roomStatus', '') || ''),
      '청소상태': String(at(raw, 'cleaningStatus', '') || ''),
      '정비유형': String(at(raw, 'cleaningType', NOVA.CLEANING_TYPES.NORMAL) || NOVA.CLEANING_TYPES.NORMAL),
      '배정유형': String(at(raw, 'assignmentType', NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO) || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO),
      '룸메이드사번': String(at(raw, 'roommaidEmployeeNo', '') || ''),
      '보조룸메이드사번': String(at(raw, 'secondaryRoommaidEmployeeNo', '') || ''),
      'QM사번': String(at(raw, 'qmEmployeeNo', '') || ''),
      '마지막변경버전': Number(at(raw, 'version', 0) || 0),
      '수정일시': String(at(raw, 'updatedAt', '') || ''),
      '하우스맨상태': '',
      '하우스맨미완료수': '',
      '객실운영상태': String(at(raw, 'operationalStatus', '') || '')
    };
  }).filter(Boolean);
}
