from pathlib import Path
import sys

BRIDGE = Path('DbFirstBridge.js')
DELAY = Path('13_DepartureDelay.js')
API = Path('04_Api.js')
CENTER = Path('NotificationCenterV1.html')
MARKER = 'DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4'


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
        "    'nova_houseman_zone_save_v1',\n    'nova_departure_delay_dashboard_v1', // DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4\n    'nova_daily_close_source_v1',",
        'departure dashboard RPC allowlist'
    )
    BRIDGE.write_text(bridge, encoding='utf-8')

text = DELAY.read_text(encoding='utf-8')
if MARKER not in text:
    legacy_sig = "function processDepartureDelayAlerts() { // (퇴실지연 자동 확인·신규 지연객실 알림)\n"
    text = replace_once(
        text,
        legacy_sig,
        "function processDepartureDelayAlertsLegacy_() { // (기존 Sheet/Telegram 수동 호환보존 · DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4)\n",
        'rename legacy delay processor'
    )
    insert_anchor = "function processDepartureDelayAlertsLegacy_() { // (기존 Sheet/Telegram 수동 호환보존 · DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4)\n"
    wrapper = r'''// DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4
function processDepartureDelayAlerts() { // (운영 자동알림은 PostgreSQL 5분 cron + NOVA 알림센터가 소유)
  return {
    ok: true,
    dbFirst: true,
    notificationNative: true,
    skipped: true,
    reason: 'DB_CRON_NATIVE',
    businessDate: Utilities.formatDate(new Date(), NOVA.TIMEZONE, NOVA.DATE_FORMAT)
  };
}

'''
    text = text.replace(insert_anchor, wrapper + insert_anchor, 1)

    old_dashboard = "function getDepartureDelayDashboard(token, options) { // (관리자·오더테이커 퇴실지연 현황 조회)\n"
    text = replace_once(
        text,
        old_dashboard,
        "function getDepartureDelayDashboardLegacy_(token, options) { // (기존 Sheet 조회 fallback · DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4)\n",
        'rename legacy delay dashboard'
    )
    legacy_dashboard_anchor = "function getDepartureDelayDashboardLegacy_(token, options) { // (기존 Sheet 조회 fallback · DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4)\n"
    dashboard_wrapper = r'''function getDepartureDelayDashboard(token, options) { // (DB 현재객실 + NOVA 알림상태 조회)
  return measureResponse_('getDepartureDelayDashboard', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
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

    old_manual = """function runDepartureDelayCheckNow(token) { // (관리자·오더테이커 수동 자동점검 실행)\n  requireRole_(token, ['ADMIN', 'ORDER']);\n  const result = processDepartureDelayAlerts();\n  return Object.assign({ message: departureDelayCheckMessage_(result) }, result);\n}\n"""
    new_manual = """function runDepartureDelayCheckNow(token) { // (DB cron 운영현황 수동 조회 · DEPARTURE_DELAY_NOTIFICATION_NATIVE_V4)\n  requireRole_(token, ['ADMIN', 'ORDER']);\n  const businessDate = Utilities.formatDate(new Date(), NOVA.TIMEZONE, NOVA.DATE_FORMAT);\n  const result = getDepartureDelayDashboard(token, { businessDate, site: '' });\n  return Object.assign({}, result, {\n    message: '퇴실지연 자동점검은 DB에서 5분 주기로 실행됩니다. 현재 DB 현황을 조회했습니다.'\n  });\n}\n"""
    text = replace_once(text, old_manual, new_manual, 'manual delay check')
    DELAY.write_text(text, encoding='utf-8')

api = API.read_text(encoding='utf-8')
if "['cleaning', 'qm', 'houseman', 'archive', 'indicator']" not in api:
    api = replace_once(
        api,
        "['cleaning', 'qm', 'houseman', 'archive']",
        "['cleaning', 'qm', 'houseman', 'archive', 'indicator']",
        'PWA indicator deep-link allowlist'
    )
    API.write_text(api, encoding='utf-8')

center = CENTER.read_text(encoding='utf-8')
if "indicator:['통합 인디케이터']" not in center:
    center = replace_once(
        center,
        "archive:['Archive 이력']},labels=map[r]||[]",
        "archive:['Archive 이력'],indicator:['통합 인디케이터']},labels=map[r]||[]",
        'notification indicator route'
    )
    CENTER.write_text(center, encoding='utf-8')

# Ensure the patch source that creates the PWA route remains compatible with a fresh baseline too.
pwa_patch = Path('scripts/patch_pwa_web_push_v2.py')
if pwa_patch.exists():
    pwa = pwa_patch.read_text(encoding='utf-8')
    if "['cleaning', 'qm', 'houseman', 'archive', 'indicator']" not in pwa:
        pwa = pwa.replace(
            "['cleaning', 'qm', 'houseman', 'archive']",
            "['cleaning', 'qm', 'houseman', 'archive', 'indicator']"
        )
        pwa_patch.write_text(pwa, encoding='utf-8')

print(f'{MARKER} applied and validated for DB cron + NOVA notification center.')
