from pathlib import Path

# Index: add bell beside user name, hidden by default for non-target roles.
index = Path('Index.html')
text = index.read_text(encoding='utf-8')
old = """      <div class=\"topbar-actions\">\n        <span id=\"userText\"></span>\n        <button id=\"logoutButton\" class=\"text-button\" type=\"button\">로그아웃</button>\n      </div>\n"""
new = """      <div class=\"topbar-actions\">\n        <span id=\"userText\"></span>\n        <button id=\"appNotificationButton\" class=\"app-notification-button hidden\" type=\"button\" aria-label=\"알림\" title=\"알림\">\n          <svg class=\"app-notification-bell\" viewBox=\"0 0 24 24\" aria-hidden=\"true\">\n            <path d=\"M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4\"></path>\n          </svg>\n          <span id=\"appNotificationBadge\" class=\"app-notification-badge hidden\">0</span>\n        </button>\n        <button id=\"logoutButton\" class=\"text-button\" type=\"button\">로그아웃</button>\n      </div>\n"""
if old not in text:
    raise SystemExit('Index topbar target not found')
text = text.replace(old, new, 1)
index.write_text(text, encoding='utf-8')

client = Path('Client.html')
text = client.read_text(encoding='utf-8')

# CSS inserted at the top of the existing inline style.
style_anchor = "<style>\n"
style = r"""<style>
  .app-notification-button {
    position: relative;
    width: 36px;
    height: 36px;
    flex: 0 0 36px;
    display: inline-grid;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 10px;
    background: transparent;
    color: #111827;
    cursor: pointer;
  }
  .app-notification-button:hover { background: #f3f4f6; }
  .app-notification-button:focus-visible { outline: 2px solid #111827; outline-offset: 2px; }
  .app-notification-bell {
    width: 21px;
    height: 21px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .app-notification-badge {
    position: absolute;
    top: 1px;
    right: -2px;
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 2px solid #fff;
    border-radius: 999px;
    background: #dc2626;
    color: #fff;
    font-size: 10px;
    font-weight: 800;
    line-height: 1;
    box-sizing: border-box;
  }
  .app-notification-panel { display: grid; gap: 12px; }
  .app-notification-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    color: #6b7280;
    font-size: 13px;
  }
  .app-notification-list {
    display: grid;
    gap: 8px;
    max-height: min(62vh, 520px);
    overflow-y: auto;
    padding-right: 2px;
  }
  .app-notification-item {
    display: grid;
    gap: 5px;
    padding: 12px 13px;
    border: 1px solid #e5e7eb;
    border-radius: 11px;
    background: #fff;
  }
  .app-notification-item-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .app-notification-item-title { font-size: 14px; font-weight: 800; color: #111827; }
  .app-notification-item-time { flex: 0 0 auto; font-size: 11px; color: #9ca3af; white-space: nowrap; }
  .app-notification-item-message { font-size: 13px; line-height: 1.45; color: #374151; word-break: keep-all; }
  .app-notification-item-meta { font-size: 11px; color: #6b7280; }
  .app-notification-empty {
    padding: 34px 12px;
    text-align: center;
    border: 1px dashed #d1d5db;
    border-radius: 11px;
    color: #9ca3af;
    font-size: 13px;
  }
  .app-notification-clear {
    width: 100%;
    min-height: 42px;
    border: 1px solid #d1d5db;
    border-radius: 10px;
    background: #fff;
    color: #374151;
    font-weight: 800;
    cursor: pointer;
  }
  .app-notification-clear:hover { background: #f9fafb; }
  .app-notification-clear:disabled { opacity: .5; cursor: default; }
  @media (max-width: 760px) {
    .topbar-actions { gap: 6px; }
    .app-notification-button { width: 38px; height: 38px; flex-basis: 38px; }
    .app-notification-bell { width: 22px; height: 22px; }
    .app-notification-list { max-height: 58vh; }
  }
"""
if style_anchor not in text:
    raise SystemExit('Client style anchor not found')
text = text.replace(style_anchor, style, 1)

# Add independent client state after realtime state object declaration.
anchor = """  const NOVA_REALTIME_ROOM_FIELDS_ = Object.freeze([\n"""
notification_state = r"""  const novaAppNotifications_ = {
    timer: null,
    busy: false,
    items: [],
    count: 0,
    lastLoadedAt: 0
  };

  function novaAppNotificationRoleEnabled_() {
    const role = String(state?.bootstrap?.user?.role || '').trim().toUpperCase();
    return ['HOUSEMAN', 'ROOMMAID', 'QM'].includes(role);
  }

  function renderAppNotificationBadge_() {
    const button = $('appNotificationButton');
    const badge = $('appNotificationBadge');
    if (!button || !badge) return;
    const enabled = novaAppNotificationRoleEnabled_();
    button.classList.toggle('hidden', !enabled);
    if (!enabled) {
      badge.classList.add('hidden');
      badge.textContent = '0';
      return;
    }
    const count = Math.max(0, Number(novaAppNotifications_.count || 0));
    badge.textContent = count > 99 ? '99+' : String(count);
    badge.classList.toggle('hidden', count <= 0);
    button.setAttribute('aria-label', count > 0 ? `알림 ${count}건` : '알림 없음');
    button.title = count > 0 ? `알림 ${count}건` : '알림';
  }

  async function loadAppNotifications_(options = {}) {
    if (!novaAppNotificationRoleEnabled_() || !state?.token) return null;
    if (novaAppNotifications_.busy && !options.force) return null;
    if (!novaRealtime_.configLoaded) await initNovaRealtime_();
    if (!novaRealtimeIsEnabled_()) return null;

    novaAppNotifications_.busy = true;
    try {
      const result = await novaRealtimeFetch_('/v1/notifications?limit=100');
      novaAppNotifications_.items = Array.isArray(result?.notifications) ? result.notifications : [];
      novaAppNotifications_.count = Math.max(0, Number(result?.count || 0));
      novaAppNotifications_.lastLoadedAt = Date.now();
      renderAppNotificationBadge_();
      return result;
    } catch (error) {
      console.error('[NOVA 알림] 조회 실패:', error);
      return null;
    } finally {
      novaAppNotifications_.busy = false;
    }
  }

  function stopAppNotificationPolling_() {
    if (novaAppNotifications_.timer) window.clearTimeout(novaAppNotifications_.timer);
    novaAppNotifications_.timer = null;
  }

  function scheduleAppNotificationPolling_(immediate = False) {
    stopAppNotificationPolling_();
    if (!novaAppNotificationRoleEnabled_() || !state?.token || !novaRealtimeIsEnabled_()) return;
    const run = async () => {
      await loadAppNotifications_();
      if (!novaAppNotificationRoleEnabled_() || !state?.token || !novaRealtimeIsEnabled_()) return;
      const base = document.hidden ? 15000 : 5000;
      const jitter = document.hidden ? 2000 : 1200;
      novaAppNotifications_.timer = window.setTimeout(run, base + Math.floor(Math.random() * jitter));
    };
    novaAppNotifications_.timer = window.setTimeout(run, immediate ? 0 : 5000);
  }

  function appNotificationListHtml_() {
    const items = Array.isArray(novaAppNotifications_.items) ? novaAppNotifications_.items : [];
    if (!items.length) return '<div class="app-notification-empty">새 알림이 없습니다.</div>';
    return items.map(item => {
      const meta = [item.businessDate, item.site, item.roomNo ? `${item.roomNo}호` : ''].filter(Boolean).join(' · ');
      return `<article class="app-notification-item">
        <div class="app-notification-item-top">
          <strong class="app-notification-item-title">${escapeHtml(item.title || '알림')}</strong>
          <span class="app-notification-item-time">${escapeHtml(item.createdAt || '')}</span>
        </div>
        ${item.message ? `<div class="app-notification-item-message">${escapeHtml(item.message)}</div>` : ''}
        ${meta ? `<div class="app-notification-item-meta">${escapeHtml(meta)}</div>` : ''}
      </article>`;
    }).join('');
  }

  function renderAppNotificationModal_() {
    const root = $('modalRoot');
    if (!root || root.classList.contains('hidden')) return;
    const body = root.querySelector('[data-app-notification-body]');
    const summary = root.querySelector('[data-app-notification-summary]');
    const clearButton = root.querySelector('[data-app-notification-clear]');
    if (body) body.innerHTML = appNotificationListHtml_();
    if (summary) summary.textContent = `보관 중 ${Math.max(0, Number(novaAppNotifications_.count || 0))}건`;
    if (clearButton) clearButton.disabled = Number(novaAppNotifications_.count || 0) <= 0;
  }

  async function openAppNotificationModal_() {
    if (!novaAppNotificationRoleEnabled_()) return;
    openModal(`<div class="modal-card">
      <div class="modal-header"><h2>알림</h2><button class="modal-close" data-close-modal>×</button></div>
      <div class="modal-body app-notification-panel">
        <div class="app-notification-summary"><span data-app-notification-summary>알림을 불러오는 중입니다.</span><span>개인 참고용</span></div>
        <div class="app-notification-list" data-app-notification-body><div class="app-notification-empty">불러오는 중…</div></div>
        <button class="app-notification-clear" type="button" data-app-notification-clear>전체 지우기</button>
      </div>
    </div>`);
    const clearButton = $('modalRoot')?.querySelector('[data-app-notification-clear]');
    if (clearButton) clearButton.addEventListener('click', clearAllAppNotifications_);
    await loadAppNotifications_({ force: true });
    renderAppNotificationModal_();
  }

  async function clearAllAppNotifications_() {
    if (!novaAppNotificationRoleEnabled_()) return;
    const count = Math.max(0, Number(novaAppNotifications_.count || 0));
    if (!count) return;
    if (!window.confirm(`알림 ${count}건을 모두 지울까요?`)) return;
    const button = $('modalRoot')?.querySelector('[data-app-notification-clear]');
    if (button) {
      button.disabled = true;
      button.textContent = '지우는 중…';
    }
    try {
      const result = await novaRealtimeFetch_('/v1/notifications/clear', {
        method: 'POST',
        body: JSON.stringify({})
      });
      if (!result?.ok) throw new Error('알림을 지우지 못했습니다.');
      novaAppNotifications_.items = [];
      novaAppNotifications_.count = 0;
      novaAppNotifications_.lastLoadedAt = Date.now();
      renderAppNotificationBadge_();
      renderAppNotificationModal_();
      showToast(`알림 ${Number(result.cleared || count)}건을 지웠습니다.`);
    } catch (error) {
      showToast(error?.message || '알림 삭제 오류');
      if (button) {
        button.disabled = false;
        button.textContent = '전체 지우기';
      }
    }
  }

  const NOVA_REALTIME_ROOM_FIELDS_ = Object.freeze([
"""
# Fix Python-style boolean in JS string before insertion.
notification_state = notification_state.replace('immediate = False', 'immediate = false')
if anchor not in text:
    raise SystemExit('Realtime fields anchor not found')
text = text.replace(anchor, notification_state, 1)

# Start polling after successful realtime initialization.
old = """      } else {\n        setSyncStatus('고속 API 연결 준비 완료');\n      }\n      return true;\n"""
new = """      } else {\n        setSyncStatus('고속 API 연결 준비 완료');\n      }\n      if (novaAppNotificationRoleEnabled_()) scheduleAppNotificationPolling_(true);\n      return true;\n"""
if old not in text:
    raise SystemExit('init realtime success anchor not found')
text = text.replace(old, new, 1)

# Render bell immediately with role gating.
old = """    $('userText').textContent = `${data.user.name} · ${data.user.job || data.user.role}`;\n    renderMenu(menuWithLostFoundShortcut_(data.menu || []));\n"""
new = """    $('userText').textContent = `${data.user.name} · ${data.user.job || data.user.role}`;\n    renderAppNotificationBadge_();\n    renderMenu(menuWithLostFoundShortcut_(data.menu || []));\n"""
if old not in text:
    raise SystemExit('renderApp anchor not found')
text = text.replace(old, new, 1)

# Bind bell click.
old = """    $('loginForm').addEventListener('submit', handleLogin);\n    $('logoutButton').addEventListener('click', handleLogout);\n"""
new = """    $('loginForm').addEventListener('submit', handleLogin);\n    $('logoutButton').addEventListener('click', handleLogout);\n    $('appNotificationButton').addEventListener('click', openAppNotificationModal_);\n"""
if old not in text:
    raise SystemExit('bindEvents anchor not found')
text = text.replace(old, new, 1)

# Stop/reset personal notification client state on logout.
old = """    stopIndicatorSync();\n    stopMobileSync();\n    void novaRealtimeDisconnect_();\n"""
new = """    stopIndicatorSync();\n    stopMobileSync();\n    stopAppNotificationPolling_();\n    novaAppNotifications_.items = [];\n    novaAppNotifications_.count = 0;\n    novaAppNotifications_.lastLoadedAt = 0;\n    renderAppNotificationBadge_();\n    void novaRealtimeDisconnect_();\n"""
if old not in text:
    raise SystemExit('handleLogout anchor not found')
text = text.replace(old, new, 1)

checks = [
    "id=\"appNotificationButton\"",
    "id=\"appNotificationBadge\"",
]
index_text = index.read_text(encoding='utf-8')
for marker in checks:
    if marker not in index_text:
        raise SystemExit(f'Index marker missing: {marker}')

client_checks = [
    "function novaAppNotificationRoleEnabled_()",
    "['HOUSEMAN', 'ROOMMAID', 'QM'].includes(role)",
    "'/v1/notifications?limit=100'",
    "'/v1/notifications/clear'",
    "function openAppNotificationModal_()",
    "function clearAllAppNotifications_()",
    "scheduleAppNotificationPolling_(true)",
    "stopAppNotificationPolling_();",
    "$('appNotificationButton').addEventListener('click', openAppNotificationModal_);",
    "renderAppNotificationBadge_();"
]
for marker in client_checks:
    if marker not in text:
        raise SystemExit(f'Client marker missing: {marker}')

client.write_text(text, encoding='utf-8')
print('PERSONAL_APP_NOTIFICATION_UI_V87_OK')
