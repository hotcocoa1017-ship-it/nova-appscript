from pathlib import Path
import sys

BRIDGE = Path('DbFirstBridge.js')
DELAY = Path('13_DepartureDelay.js')
MARKER = 'DEPARTURE_DELAY_DB_FIRST_APP_V3'


def fail(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    raise SystemExit(94)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        if count == 0 and new in text:
            return text
        fail(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)

bridge = BRIDGE.read_text(encoding='utf-8')
if "'nova_departure_delay_dashboard_v1'" not in bridge:
    bridge = replace_once(
        bridge,
        "    'nova_houseman_zone_save_v1',\n    'nova_daily_close_source_v1',",
        "    'nova_houseman_zone_save_v1',\n    'nova_departure_delay_dashboard_v1', // DEPARTURE_DELAY_DB_FIRST_APP_V3\n    'nova_daily_close_source_v1',",
        'departure dashboard RPC allowlist'
    )
    BRIDGE.write_text(bridge, encoding='utf-8')

text = DELAY.read_text(encoding='utf-8')
if MARKER in text:
    print(f'{MARKER} already applied.')
    raise SystemExit(0)

legacy_sig = "function processDepartureDelayAlerts() { // (퇴실지연 자동 확인·신규 지연객실 알림)\n"
text = replace_once(
    text,
    legacy_sig,
    "function processDepartureDelayAlertsLegacy_() { // (기존 Sheet-first fallback · DEPARTURE_DELAY_DB_FIRST_APP_V3)\n",
    'rename legacy delay processor'
)

insert_anchor = "function processDepartureDelayAlertsLegacy_() { // (기존 Sheet-first fallback · DEPARTURE_DELAY_DB_FIRST_APP_V3)\n"
wrapper = r'''// DEPARTURE_DELAY_DB_FIRST_APP_V3
const NOVA_DEPARTURE_DELAY_SYSTEM_EDGE_ = 'https://evoetxfjmkkjptucwxsv.supabase.co/functions/v1/nova-departure-delay-system-v1';

function novaDepartureDelaySystemPost_(action, payload) { // (SYSTEM 전용 claim/finalize · 브라우저 비밀값 미노출)
  if (typeof novaArchiveAdminKey_ !== 'function') {
    return { ok: false, legacyFallback: true, reason: 'SYSTEM_KEY_UNAVAILABLE' };
  }
  const bodyText = JSON.stringify({ action: String(action || '').trim(), payload: payload || {} });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    let response;
    try {
      response = UrlFetchApp.fetch(NOVA_DEPARTURE_DELAY_SYSTEM_EDGE_, {
        method: 'post',
        contentType: 'application/json; charset=utf-8',
        headers: { 'X-NOVA-System-Key': novaArchiveAdminKey_() },
        payload: bodyText,
        muteHttpExceptions: true,
        followRedirects: true
      });
    } catch (networkError) {
      if (attempt < 2) {
        Utilities.sleep([180, 450, 900][attempt] || 900);
        continue;
      }
      const error = new Error('퇴실지연 DB 처리 결과를 확인할 수 없습니다. 다음 자동점검에서 DB claim 상태를 다시 확인합니다.');
      error.code = 'DEPARTURE_DELAY_DB_RESULT_UNKNOWN';
      throw error;
    }
    const status = Number(response.getResponseCode() || 0);
    let data = {};
    try { data = JSON.parse(response.getContentText('UTF-8') || '{}'); } catch (ignore) { data = {}; }
    if (status >= 200 && status < 300 && data && data.ok) return data;
    if (status === 404 && String(action || '').trim().toLowerCase() === 'claim') {
      return { ok: false, legacyFallback: true, reason: 'EDGE_MISSING' };
    }
    if ((status === 429 || status >= 500) && attempt < 2) {
      Utilities.sleep([180, 450, 900][attempt] || 900);
      continue;
    }
    const error = new Error(String(data && (data.message || data.error) || `퇴실지연 DB 서버 오류 (${status || 'NO_STATUS'})`));
    error.code = String(data && data.code || 'DEPARTURE_DELAY_DB_FAILED');
    error.status = status;
    throw error;
  }
  throw new Error('퇴실지연 DB 요청을 완료하지 못했습니다.');
}

function processDepartureDelayAlerts() { // (DB claim -> Telegram -> Sheet 호환이력 -> DB finalize)
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(3000)) return { ok: false, skipped: true, reason: 'LOCKED' };
  try {
    const businessDate = Utilities.formatDate(new Date(), NOVA.TIMEZONE, NOVA.DATE_FORMAT);
    const claimToken = `DDCLAIM-${businessDate.replaceAll('-', '')}-${Utilities.getUuid()}`;
    let claim;
    try {
      claim = novaDepartureDelaySystemPost_('claim', { businessDate, claimToken });
    } catch (error) {
      if (String(error && error.code || '') === 'DEPARTURE_DELAY_DB_RESULT_UNKNOWN') {
        console.warn('[NOVA DB] 퇴실지연 claim 결과불명 · legacy 이중처리 금지:', error.message || error);
        return { ok: false, skipped: true, reason: 'DB_RESULT_UNKNOWN', businessDate };
      }
      throw error;
    }
    if (claim && claim.legacyFallback) return processDepartureDelayAlertsLegacy_();
    if (!claim || !claim.ok) throw new Error(claim && claim.message || '퇴실지연 DB claim에 실패했습니다.');
    const rule = claim.rule || getDepartureDelayRule_(businessDate, new Date());
    if (claim.ready === false) return { ok: true, skipped: true, reason: claim.reason || 'DB_NOT_READY', businessDate, rule };
    if (claim.reached === false) return { ok: true, skipped: true, reason: 'BEFORE_ALERT_TIME', businessDate, rule };

    const claimedRooms = Array.isArray(claim.items) ? claim.items : [];
    if (!claimedRooms.length) return { ok: true, processedSites: 0, notifiedRooms: 0, businessDate, rule, dbFirst: true };

    // DB finalize 응답이 유실됐던 직전 실행은 기존 Sheet 호환이력을 이용해 Telegram 중복을 막습니다.
    const sheetNotified = getDepartureDelayNotificationIndex_(businessDate);
    const bySite = {};
    claimedRooms.forEach(room => {
      const site = String(room && room.site || '').trim();
      const roomNo = String(room && room.roomNo || '').trim();
      if (!site || !roomNo) return;
      if (!bySite[site]) bySite[site] = [];
      bySite[site].push({
        roomNo,
        site,
        building: String(room.building || '').trim(),
        roomStatus: 'DUE_OUT'
      });
    });

    const finalizeResults = [];
    const mirroredRows = [];
    const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const version = getDataVersion_();
    let processedSites = 0;
    let notifiedRooms = 0;

    Object.keys(bySite).sort((a, b) => a.localeCompare(b, 'ko')).forEach(site => {
      const rooms = bySite[site].sort((a, b) => compareDepartureRoomNos_(a.roomNo, b.roomNo));
      const alreadyMirrored = [];
      const pending = [];
      rooms.forEach(room => {
        const key = departureDelayKey_(businessDate, site, room.roomNo);
        (sheetNotified.keys.has(key) ? alreadyMirrored : pending).push(room);
      });
      alreadyMirrored.forEach(room => finalizeResults.push({ site, roomNo: room.roomNo, ok: true, recipientCount: 0, recoveredFromSheetMirror: true }));
      if (!pending.length) return;

      const recipients = resolveDepartureDelayTelegramRecipients_(site);
      if (!recipients.length) {
        pending.forEach(room => finalizeResults.push({ site, roomNo: room.roomNo, ok: false, recipientCount: 0, error: 'NO_RECIPIENTS' }));
        return;
      }
      const queued = queueTelegramNotification_({
        notificationType: 'DEPARTURE_DELAY',
        businessDate,
        site,
        recipients,
        message: buildDepartureDelayTelegramMessage_(businessDate, site, pending, rule),
        eventName: 'DEPARTURE_DELAY',
        parentRecordId: `DELAY-${businessDate}-${site}`,
        registeredBy: 'SYSTEM',
        version
      });
      if (!queued || !queued.queued) {
        pending.forEach(room => finalizeResults.push({ site, roomNo: room.roomNo, ok: false, recipientCount: recipients.length, error: 'TELEGRAM_QUEUE_FAILED' }));
        return;
      }

      const registeredAt = nowText_();
      pending.forEach(room => {
        finalizeResults.push({ site, roomNo: room.roomNo, ok: true, recipientCount: recipients.length });
        mirroredRows.push(createRowByHeaders_(historySheet, {
          '기록ID': `DD-${businessDate.replaceAll('-', '')}-${Utilities.getUuid().slice(0, 10).toUpperCase()}`,
          '기록구분': NOVA.RECORD_TYPES.DEPARTURE_DELAY,
          '업무일자': businessDate,
          '사업장': site,
          '객실번호': room.roomNo,
          '처리상태': 'NOTIFIED',
          '세부내용JSON': JSON.stringify({
            source: 'DEPARTURE_DELAY_DB_FIRST_APP_V3',
            notificationType: 'DEPARTURE_DELAY',
            alertTime: rule.alertTime,
            checkoutTime: rule.checkoutTime,
            dayType: rule.dayType,
            building: room.building,
            recipientCount: recipients.length,
            claimToken
          }),
          '등록사번': 'SYSTEM',
          '등록일시': registeredAt,
          '수정일시': registeredAt,
          '변경버전': version,
          '삭제여부': 'N'
        }));
      });
      processedSites += 1;
      notifiedRooms += pending.length;
    });

    // 호환이력 실패가 DB 알림확정을 되돌리면 안 됩니다. 기록 실패는 경고 후 DB finalize를 계속합니다.
    if (mirroredRows.length) {
      try {
        const startRow = historySheet.getLastRow() + 1;
        ensureSheetRowCapacity_(historySheet, startRow + mirroredRows.length - 1);
        historySheet.getRange(startRow, 1, mirroredRows.length, mirroredRows[0].length).setValues(mirroredRows);
      } catch (mirrorError) {
        console.warn('[NOVA DB] 퇴실지연 Sheet 호환이력 미러 지연:', mirrorError && mirrorError.message || mirrorError);
      }
    }

    try {
      novaDepartureDelaySystemPost_('finalize', { claimToken, results: finalizeResults });
    } catch (finalizeError) {
      console.warn('[NOVA DB] 퇴실지연 finalize 지연 · stale claim 재처리 예정:', finalizeError && finalizeError.message || finalizeError);
    }
    return { ok: true, dbFirst: true, businessDate, rule, processedSites, notifiedRooms, claimedRooms: claimedRooms.length };
  } finally {
    lock.releaseLock();
  }
}

'''
text = text.replace(insert_anchor, wrapper + insert_anchor, 1)

old_dashboard = "function getDepartureDelayDashboard(token, options) { // (관리자·오더테이커 퇴실지연 현황 조회)\n"
text = replace_once(
    text,
    old_dashboard,
    "function getDepartureDelayDashboardLegacy_(token, options) { // (기존 Sheet 조회 fallback · DEPARTURE_DELAY_DB_FIRST_APP_V3)\n",
    'rename legacy delay dashboard'
)
legacy_dashboard_anchor = "function getDepartureDelayDashboardLegacy_(token, options) { // (기존 Sheet 조회 fallback · DEPARTURE_DELAY_DB_FIRST_APP_V3)\n"
dashboard_wrapper = r'''function getDepartureDelayDashboard(token, options) { // (DB 현재객실 + DB 알림상태 조회)
  return measureResponse_('getDepartureDelayDashboard', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = options || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    const db = novaDbFirstRpc_(token, 'nova_departure_delay_dashboard_v1', {
      p_business_date: businessDate,
      p_site: site
    }, { readOnly: true, allowLegacyFallback: true });
    if (db && db.ok) return db;
    if (db && db.legacyFallback) return getDepartureDelayDashboardLegacy_(token, options);
    throw new Error(db && db.message || '퇴실지연 DB 현황을 불러오지 못했습니다.');
  });
}

'''
text = text.replace(legacy_dashboard_anchor, dashboard_wrapper + legacy_dashboard_anchor, 1)

DELAY.write_text(text, encoding='utf-8')
print(f'{MARKER} applied.')
