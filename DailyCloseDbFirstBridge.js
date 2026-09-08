/** NOVA_DAILY_CLOSE_DB_FIRST_V3 */
function novaDailyCloseDbSummary_(item) {
  const safe = item || {};
  const snapshot = safe.snapshot && typeof safe.snapshot === 'object' ? safe.snapshot : {};
  return Object.assign({}, snapshot, {
    businessDate: String(safe.businessDate || snapshot.businessDate || '').trim(),
    site: String(safe.site || snapshot.site || '').trim(),
    closedAt: String(safe.closedAt || snapshot.closedAt || '').trim(),
    closedBy: String(safe.closedBy || snapshot.closedBy || '').trim(),
    closedByName: String(safe.closedByName || snapshot.closedByName || '').trim(),
    sourceSignature: String(safe.sourceSignature || snapshot.sourceSignature || '').trim(),
    sourceUpdatedAt: String(safe.sourceUpdatedAt || snapshot.sourceUpdatedAt || '').trim(),
    source: 'CLOSED',
    dbFirst: true,
    dbVersion: Number(safe.version || 0)
  });
}

function novaDailyCloseSourceDbFirst_(token, businessDate, site) {
  return novaDbFirstRpc_(token, 'nova_daily_close_source_v1', {
    p_business_date: normalizeBusinessDate_(businessDate),
    p_site: String(site || '').trim()
  }, { readOnly: true, allowLegacyFallback: true });
}

// ROOMMAID_CLOSE_SAVE_DB_FIRST_V1
// V4 이전 업로드로 DB snapshot만 없는 업무일은 DB 현재객실을 유지하고,
// Sheet에서 최종 ROOM_STATUS_UPLOAD 원본 메타데이터 1건만 보강합니다.
function novaDailyCloseLegacyUploadCompatSource_(source, businessDate, site) {
  const safe = source && typeof source === 'object' ? source : {};
  if (safe.ready === true) return safe;
  const reasons = (Array.isArray(safe.reasons) ? safe.reasons : []).map(value => String(value || '').trim()).filter(Boolean);
  const allowedReasons = new Set(['ACTIVE_UPLOAD_SNAPSHOT_MISSING', 'ROOM_COUNT_MISMATCH']);
  if (!reasons.length || reasons.some(reason => !allowedReasons.has(reason))) return safe;

  const metrics = safe.metrics && typeof safe.metrics === 'object' ? safe.metrics : {};
  const roomCount = Number(metrics.rooms || 0);
  if (roomCount <= 0 || Number(metrics.activeUploads || 0) !== 0) return safe;

  const bundle = readRoommaidCloseHistoryBundleFast_(normalizeBusinessDate_(businessDate), String(site || '').trim());
  const uploads = (Array.isArray(bundle && bundle.historyRows) ? bundle.historyRows : [])
    .filter(row => String(row && row['기록구분'] || '').trim() === NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD)
    .filter(row => String(row && row['처리상태'] || '').trim().toUpperCase() === 'APPLIED')
    .filter(row => String(row && row['삭제여부'] || 'N').trim().toUpperCase() !== 'Y')
    .sort((a, b) => Number(b && b['변경버전'] || 0) - Number(a && a['변경버전'] || 0)
      || String(b && b['등록일시'] || '').localeCompare(String(a && a['등록일시'] || '')));
  const upload = uploads[0] || null;
  if (!upload) return safe;

  const detail = parseHistoryDetailSafe_(upload);
  const uploadTotal = Number(detail && detail.totalRooms || 0);
  const roomsByStatus = detail && detail.roomsByStatus && typeof detail.roomsByStatus === 'object' ? detail.roomsByStatus : {};
  if (!uploadTotal || uploadTotal !== roomCount || !Object.keys(roomsByStatus).length) return safe;

  const dbHistory = (Array.isArray(safe.historyRows) ? safe.historyRows : [])
    .filter(row => String(row && row['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD);
  return Object.assign({}, safe, {
    ready: true,
    reasons: [],
    historyRows: [upload].concat(dbHistory),
    metrics: Object.assign({}, metrics, { activeUploads: 1, uploadTotalRooms: uploadTotal, legacyUploadCompat: true }),
    compatibility: Object.assign({}, safe.compatibility || {}, {
      legacyUploadSnapshot: true,
      uploadVersion: Number(upload['변경버전'] || 0),
      uploadRegisteredAt: String(upload['등록일시'] || '').trim()
    })
  });
}

function novaDailyCloseBuildFromDbSource_(source, user, attendanceEmployeeNos, includeRooms) {
  const businessDate = normalizeBusinessDate_(source.businessDate);
  const site = String(source.site || '').trim();
  const currentRows = Array.isArray(source.currentRows) ? source.currentRows : [];
  const historyRows = Array.isArray(source.historyRows) ? source.historyRows : [];
  validateRoommaidCloseIntegrityForSave_(businessDate, site, currentRows, historyRows);
  const snapshot = buildDailyCloseSnapshot_(businessDate, site, {
    closedBy: String(user && user.employeeNo || '').trim(),
    closedByName: String(user && user.name || '').trim(),
    closedAt: nowText_(),
    includeRooms: includeRooms !== false,
    currentRows,
    historyRows,
    attendanceEmployeeNos: Array.isArray(attendanceEmployeeNos) ? attendanceEmployeeNos : []
  });
  if (!snapshot.totalRooms) throw new Error(`${businessDate} ${site} DB 현재객실현황이 없습니다.`);
  return snapshot;
}

function novaDailyCloseMirrorSnapshotToSheet_(businessDate, site, user, snapshot, dbResult) { // (DB snapshot 그대로 Sheet 호환이력 저장)
  const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const closedAt = String(snapshot.closedAt || nowText_()).trim() || nowText_();
  const lock = acquireWriteLock_(30000);
  try {
    markExistingDailyCloseDeleted_(historySheet, businessDate, site, closedAt);
    const version = reserveDataVersion_({ lockHeld: true });
    const batchId = `DC-${businessDate.replaceAll('-', '')}-${dailyCloseSafeId_(site)}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`;
    const summaryDetail = Object.assign({}, snapshot, {
      dbFirst: true,
      dbRequestId: String(dbResult && dbResult.requestId || '').trim(),
      dbVersion: Number(dbResult && dbResult.version || 0),
      source: 'NOVA_DAILY_CLOSE_DB_FIRST_V3'
    });
    delete summaryDetail.rooms;
    summaryDetail.roommaidCloseJournal = compactRoommaidCloseJournalForStorage_(snapshot.roommaidCloseJournal);
    const summaryJson = JSON.stringify(summaryDetail);
    if (summaryJson.length > NOVA_DAILY_CLOSE.MAX_JSON_LENGTH) throw new Error(`${site} 마감 요약 데이터가 너무 큽니다.`);

    const rows = [createRowByHeaders_(historySheet, {
      '기록ID': `${batchId}-SUMMARY`,
      '기록구분': NOVA.RECORD_TYPES.DAILY_CLOSE,
      '업무일자': businessDate,
      '사업장': site,
      '처리상태': NOVA_DAILY_CLOSE.SUMMARY_STATUS,
      '세부내용JSON': summaryJson,
      '등록사번': String(user && user.employeeNo || '').trim(),
      '등록일시': closedAt,
      '수정일시': closedAt,
      '변경버전': version,
      '삭제여부': 'N'
    })];
    chunkArray_(snapshot.rooms || [], NOVA_DAILY_CLOSE.ROOM_CHUNK_SIZE).forEach((chunk, index) => {
      const status = `${NOVA_DAILY_CLOSE.ROOM_STATUS_PREFIX}${String(index + 1).padStart(3, '0')}`;
      const detail = JSON.stringify({
        schemaVersion: NOVA_DAILY_CLOSE.SCHEMA_VERSION,
        batchId,
        chunkIndex: index + 1,
        dbFirst: true,
        dbRequestId: String(dbResult && dbResult.requestId || '').trim(),
        rooms: chunk
      });
      if (detail.length > NOVA_DAILY_CLOSE.MAX_JSON_LENGTH) throw new Error(`${site} 객실 스냅샷 ${index + 1}번 묶음이 너무 큽니다.`);
      rows.push(createRowByHeaders_(historySheet, {
        '기록ID': `${batchId}-${status}`,
        '기록구분': NOVA.RECORD_TYPES.DAILY_CLOSE,
        '업무일자': businessDate,
        '사업장': site,
        '처리상태': status,
        '세부내용JSON': detail,
        '등록사번': String(user && user.employeeNo || '').trim(),
        '등록일시': closedAt,
        '수정일시': closedAt,
        '변경버전': version,
        '삭제여부': 'N'
      }));
    });
    const startRow = historySheet.getLastRow() + 1;
    ensureSheetRowCapacity_(historySheet, startRow + rows.length - 1);
    historySheet.getRange(startRow, 1, rows.length, rows[0].length).setValues(rows);
    SpreadsheetApp.flush();
    publishDataVersion_(version, { domains: ['REPORT'], businessDate, site, lockHeld: true });
    return { ok: true, version, chunkCount: rows.length - 1 };
  } finally {
    lock.releaseLock();
  }
}

function saveDailyCloseSnapshotDbFirst(token, payload) { // (DB source -> 기존 산식 -> DB close -> Sheet mirror)
  return measureResponse_('saveDailyCloseSnapshotDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const requestedSite = String(safe.site || '').trim();
    const candidates = requestedSite ? [requestedSite] : getSiteList_();
    if (!candidates.length) throw new Error('마감할 사업장이 없습니다.');

    // Every source is checked before the first DB write. No mixed Sheet/DB partial start.
    const prepared = [];
    let mustLegacyFallback = false;
    candidates.forEach(site => {
      const rawSource = novaDailyCloseSourceDbFirst_(token, businessDate, site);
      const source = safe.roommaidCloseCompat === true
        ? novaDailyCloseLegacyUploadCompatSource_(rawSource, businessDate, site)
        : rawSource; // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1
      if (source && source.legacyFallback) {
        mustLegacyFallback = true;
        return;
      }
      const metrics = source && source.metrics || {};
      if (source && source.ready === false) {
        if (Number(metrics.rooms || 0) === 0) return;
        const reasons = Array.isArray(source.reasons) ? source.reasons.join(', ') : String(source.reason || 'DB_NOT_READY');
        throw new Error(`${businessDate} ${site} DB 마감원본 정합검증 실패: ${reasons}`);
      }
      if (!source || !source.ok || source.ready !== true) throw new Error(`${businessDate} ${site} DB 마감원본을 준비하지 못했습니다.`);
      const snapshot = novaDailyCloseBuildFromDbSource_(source, user, safe.attendanceEmployeeNos, true);
      prepared.push({ site, source, snapshot });
    });
    if (mustLegacyFallback) return saveDailyCloseSnapshot(token, payload);
    if (!prepared.length) throw new Error(`${businessDate} DB 현재객실현황에 마감할 사업장이 없습니다.`);

    const results = [];
    let saveLegacyFallback = false; // DAILY_CLOSE_SAVE_FALLBACK_FAILSAFE_V1
    prepared.forEach(item => {
      if (saveLegacyFallback) return;
      const requestId = String(safe.requestId || novaDbFirstRequestId_(`DAILY_CLOSE_${item.site}`)).trim();
      const db = novaDbFirstRpc_(token, 'nova_daily_close_save_v2', {
        p_business_date: businessDate,
        p_site: item.site,
        p_snapshot: item.snapshot,
        p_request_id: requestId
      }, { allowLegacyFallback: true });
      if (db && db.legacyFallback) {
        if (results.length) throw new Error('일부 사업장 DB 마감이 이미 확정되어 legacy 저장으로 전환할 수 없습니다.');
        saveLegacyFallback = true;
        return;
      }
      let mirror = null;
      try { mirror = novaDailyCloseMirrorSnapshotToSheet_(businessDate, item.site, user, item.snapshot, db); }
      catch (mirrorError) {
        console.warn('[NOVA DB] 일마감 DB 확정 후 Sheet 미러 지연:', mirrorError && mirrorError.message || mirrorError);
        db.sheetMirrorPending = true;
      }
      results.push(Object.assign({}, db, { site: item.site, snapshot: Object.assign({}, item.snapshot, { rooms: undefined }), mirror }));
    });
    if (saveLegacyFallback) return saveDailyCloseSnapshot(token, payload);
    if (!results.length && mustLegacyFallback) return saveDailyCloseSnapshot(token, payload);
    return {
      ok: true,
      dbFirst: true,
      businessDate,
      sites: results,
      message: `${businessDate} ${results.length}개 사업장의 DB 마감자료를 저장했습니다.`
    };
  });
}

function saveRoommaidCloseJournalDbFirst(token, payload) { // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1
  return measureResponse_('saveRoommaidCloseJournalDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('마감할 사업장을 선택하세요.');
    const result = saveDailyCloseSnapshotDbFirst(token, {
      businessDate,
      site,
      attendanceEmployeeNos: uniqueEmployeeNos_(safe.attendanceEmployeeNos || []),
      requestId: String(safe.requestId || '').trim(),
      roommaidCloseCompat: true
    });
    if (!result || result.ok !== true) throw new Error(result && result.message || '룸메이드 마감일지를 저장하지 못했습니다.');
    const siteResult = Array.isArray(result.sites)
      ? result.sites.find(item => String(item && item.site || '').trim() === site) || result.sites[0]
      : null;
    const snapshot = siteResult && siteResult.snapshot && typeof siteResult.snapshot === 'object' ? siteResult.snapshot : {};
    return {
      ok: true,
      dbFirst: result.dbFirst === true,
      businessDate,
      site,
      closedAt: String(snapshot.closedAt || siteResult && siteResult.closedAt || '').trim(),
      message: `${businessDate} ${site} 룸메이드 마감일지를 저장했습니다.`
    };
  });
}

function resetRoommaidCloseJournalDbFirst(token, payload) { // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1
  return measureResponse_('resetRoommaidCloseJournalDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('초기화할 사업장을 선택하세요.');
    const requestId = String(safe.requestId || novaDbFirstRequestId_(`ROOMMAID_CLOSE_CANCEL_${site}`)).trim();
    const db = novaDbFirstRpc_(token, 'nova_roommaid_close_cancel_v1', {
      p_business_date: businessDate,
      p_site: site,
      p_reason: 'ROOMMAID_CLOSE_RESET',
      p_request_id: requestId
    }, { allowLegacyFallback: true });

    if (db && db.legacyFallback) return resetRoommaidCloseJournal(token, payload);
    if (!db || db.ok !== true) throw new Error(db && db.message || '룸메이드 마감자료를 초기화하지 못했습니다.');
    if (db.noDbSnapshot === true) return resetRoommaidCloseJournal(token, payload);

    let mirror = null;
    try { mirror = resetRoommaidCloseJournal(token, payload); }
    catch (error) { console.warn('[NOVA DB] 룸메이드 마감 DB 취소 후 Sheet 미러 지연:', error && error.message || error); }
    const mirrorOk = Boolean(mirror && mirror.ok === true);
    return {
      ok: true,
      dbFirst: true,
      businessDate,
      site,
      resetCount: Number(mirrorOk ? mirror.resetCount : db.cancelledCount || 1),
      resetBy: String(db.cancelledBy || '').trim(),
      resetAt: nowText_(),
      sheetMirrorPending: !mirrorOk,
      message: `${businessDate} ${site} 룸메이드 마감자료를 초기화했습니다. 현재 자료를 확인한 후 다시 마감하세요.`
    };
  });
}

function buildDailyCloseOverviewDbFirst_(token, request) { // (DB close 우선 + 비전환 과거일만 legacy 보존)
  const startDate = request.period === 'DAILY'
    ? request.date
    : `${request.year}-${String(request.month).padStart(2, '0')}-01`;
  const endDate = request.period === 'DAILY'
    ? request.date
    : Utilities.formatDate(new Date(request.year, request.month, 0), NOVA.TIMEZONE, NOVA.DATE_FORMAT);
  const db = novaDbFirstRpc_(token, 'nova_daily_close_read_v1', {
    p_start_date: startDate,
    p_end_date: endDate,
    p_site: request.site
  }, { readOnly: true, allowLegacyFallback: true });
  if (db && db.legacyFallback) return buildDailyCloseOverviewForRequest_(request);
  const dbItems = (Array.isArray(db && db.items) ? db.items : []).map(novaDailyCloseDbSummary_);
  const dbKeys = new Set(dbItems.map(item => `${item.businessDate}|${item.site}`));

  if (request.period === 'MONTHLY') {
    const legacy = buildDailyCloseMonthlyOverview_(request);
    const oldItems = (legacy.sites || []).filter(item => !dbKeys.has(`${item.businessDate}|${item.site}`));
    const items = oldItems.concat(dbItems).sort((a, b) => String(a.businessDate).localeCompare(String(b.businessDate)) || String(a.site).localeCompare(String(b.site), 'ko'));
    return {
      period: 'MONTHLY', year: request.year, month: request.month, site: request.site,
      source: items.length ? (dbItems.length ? 'DB+CLOSED' : 'CLOSED') : 'NONE',
      isClosed: Boolean(items.length),
      closedDays: new Set(items.map(item => item.businessDate)).size,
      summary: aggregateDailyCloseSummaries_(items), sites: items,
      message: items.length ? '' : '선택한 월에 저장된 공식 마감자료가 없습니다.', dbFirst: Boolean(dbItems.length)
    };
  }

  const closedBySite = {};
  dbItems.forEach(item => { closedBySite[item.site] = item; });
  const sites = request.site ? [request.site] : getSiteList_();
  const items = [];
  let liveFallbackNeeded = false;
  sites.forEach(site => {
    if (closedBySite[site]) { items.push(closedBySite[site]); return; }
    const source = novaDailyCloseSourceDbFirst_(token, request.date, site);
    if (source && source.legacyFallback) { liveFallbackNeeded = true; return; }
    const metrics = source && source.metrics || {};
    if (source && source.ready === false) {
      if (Number(metrics.rooms || 0) === 0) return;
      liveFallbackNeeded = true;
      return;
    }
    if (!source || source.ready !== true) { liveFallbackNeeded = true; return; }
    const live = buildDailyCloseSnapshot_(request.date, site, {
      closedBy: '', closedByName: '', closedAt: '', includeRooms: false,
      currentRows: Array.isArray(source.currentRows) ? source.currentRows : [],
      historyRows: Array.isArray(source.historyRows) ? source.historyRows : []
    });
    items.push(Object.assign({ source: 'LIVE', dbFirst: true }, live));
  });
  if (liveFallbackNeeded && !dbItems.length) return buildDailyCloseDailyOverview_(request);
  return {
    period: 'DAILY', businessDate: request.date, site: request.site,
    source: dailyCloseSourceLabel_(items),
    isClosed: Boolean(items.length && items.every(item => item.source === 'CLOSED')),
    closedAt: latestText_(items.map(item => item.closedAt)),
    closedBy: items.length === 1 ? String(items[0].closedByName || items[0].closedBy || '') : '',
    summary: aggregateDailyCloseSummaries_(items), sites: items,
    message: items.length ? '' : `${request.date} 마감통계 자료가 없습니다.`, dbFirst: true
  };
}

function getDailyCloseOverviewDbFirst(token, filters) {
  return measureResponse_('getDailyCloseOverviewDbFirst', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const request = normalizeMonthlyFilters_(filters || {}, user);
    return Object.assign({ ok: true }, buildDailyCloseOverviewDbFirst_(token, request));
  });
}
