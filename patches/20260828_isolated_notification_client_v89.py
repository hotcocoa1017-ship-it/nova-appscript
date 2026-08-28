from pathlib import Path

index = Path('Index.html')
text = index.read_text(encoding='utf-8')
include_anchor = "  <?!= include_('HousemanRequestPhotoClient'); ?>\n"
include_line = "  <?!= include_('NotificationClient'); ?>\n"
if include_line not in text:
    if include_anchor not in text:
        raise SystemExit('Index notification include anchor not found')
    text = text.replace(include_anchor, include_anchor + include_line, 1)
index.write_text(text, encoding='utf-8')

notification = Path('NotificationClient.html')
notification.write_text(r'''<style>
  .nova-notification-button {
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
  .nova-notification-button:hover { background: #f3f4f6; }
  .nova-notification-button:focus-visible { outline: 2px solid #111827; outline-offset: 2px; }
  .nova-notification-bell {
    width: 21px;
    height: 21px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .nova-notification-badge {
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
  .nova-notification-overlay {
    position: fixed;
    inset: 0;
    z-index: 10050;
    display: grid;
    place-items: center;
    padding: 18px;
    background: rgba(17,24,39,.42);
  }
  .nova-notification-card {
    width: min(520px, 100%);
    max-height: min(78vh, 650px);
    display: grid;
    grid-template-rows: auto minmax(0,1fr) auto;
    overflow: hidden;
    border-radius: 16px;
    background: #fff;
    box-shadow: 0 18px 50px rgba(0,0,0,.18);
  }
  .nova-notification-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 16px 18px;
    border-bottom: 1px solid #e5e7eb;
  }
  .nova-notification-header strong { font-size: 16px; }
  .nova-notification-close {
    width: 34px;
    height: 34px;
    border: 0;
    border-radius: 9px;
    background: #f3f4f6;
    color: #374151;
    font-size: 20px;
    cursor: pointer;
  }
  .nova-notification-body {
    min-height: 0;
    overflow-y: auto;
    display: grid;
    align-content: start;
    gap: 8px;
    padding: 14px 16px;
  }
  .nova-notification-summary {
    margin-bottom: 4px;
    color: #6b7280;
    font-size: 12px;
  }
  .nova-notification-item {
    display: grid;
    gap: 5px;
    padding: 12px 13px;
    border: 1px solid #e5e7eb;
    border-radius: 11px;
    background: #fff;
  }
  .nova-notification-item-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .nova-notification-item-title { font-size: 14px; font-weight: 800; color: #111827; }
  .nova-notification-item-time { flex: 0 0 auto; font-size: 11px; color: #9ca3af; white-space: nowrap; }
  .nova-notification-item-message { font-size: 13px; line-height: 1.45; color: #374151; word-break: keep-all; }
  .nova-notification-item-meta { font-size: 11px; color: #6b7280; }
  .nova-notification-empty {
    padding: 38px 12px;
    text-align: center;
    border: 1px dashed #d1d5db;
    border-radius: 11px;
    color: #9ca3af;
    font-size: 13px;
  }
  .nova-notification-footer { padding: 12px 16px 16px; border-top: 1px solid #f3f4f6; }
  .nova-notification-clear {
    width: 100%;
    min-height: 42px;
    border: 1px solid #d1d5db;
    border-radius: 10px;
    background: #fff;
    color: #374151;
    font-weight: 800;
    cursor: pointer;
  }
  .nova-notification-clear:disabled { opacity: .5; cursor: default; }
  @media (max-width: 760px) {
    .nova-notification-button { width: 38px; height: 38px; flex-basis: 38px; }
    .nova-notification-card { max-height: 82vh; }
  }
</style>
<script>
(() => {
  'use strict';

  // 중요: 이 모듈은 NOVA 핵심 Client 초기화와 완전히 분리되어 있습니다.
  // 오류가 나더라도 로그인/메인 진입을 차단하지 않도록 DOMContentLoaded 이후 별도 실행합니다.
  const allowedRoles = new Set(['HOUSEMAN', 'ROOMMAID', 'QM']);
  const model = {
    active: false,
    busy: false,
    timer: null,
    token: '',
    apiBase: '',
    role: '',
    count: 0,
    items: []
  };

  const byId = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\"/g, '&quot;')
    .replace(/'/g, '&#39;');

  function gsCall(method, ...args) {
    return new Promise((resolve, reject) => {
      try {
        const runner = google.script.run
          .withSuccessHandler(resolve)
          .withFailureHandler(error => reject(new Error(error?.message || String(error || '서버 호출 오류'))));
        runner[method](...args);
      } catch (error) {
        reject(error);
      }
    });
  }

  function mainVisible() {
    const main = byId('mainView');
    return Boolean(main && !main.classList.contains('hidden'));
  }

  function removeButton() {
    byId('novaNotificationButton')?.remove();
  }

  function ensureButton() {
    if (!allowedRoles.has(model.role)) return removeButton();
    let button = byId('novaNotificationButton');
    if (button) return button;
    const actions = document.querySelector('#mainView .topbar-actions');
    const logout = byId('logoutButton');
    if (!actions || !logout) return null;
    button = document.createElement('button');
    button.id = 'novaNotificationButton';
    button.className = 'nova-notification-button';
    button.type = 'button';
    button.setAttribute('aria-label', '알림');
    button.title = '알림';
    button.innerHTML = '<svg class="nova-notification-bell" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"></path></svg><span id="novaNotificationBadge" class="nova-notification-badge" style="display:none">0</span>';
    button.addEventListener('click', openPanel);
    actions.insertBefore(button, logout);
    return button;
  }

  function renderBadge() {
    const button = ensureButton();
    const badge = byId('novaNotificationBadge');
    if (!button || !badge) return;
    const count = Math.max(0, Number(model.count || 0));
    badge.textContent = count > 99 ? '99+' : String(count);
    badge.style.display = count > 0 ? 'inline-flex' : 'none';
    button.setAttribute('aria-label', count > 0 ? `알림 ${count}건` : '알림 없음');
    button.title = count > 0 ? `알림 ${count}건` : '알림';
  }

  async function apiFetch(path, options = {}) {
    if (!model.apiBase || !model.token) throw new Error('알림 서버 연결정보가 없습니다.');
    const response = await fetch(`${model.apiBase}${path}`, {
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${model.token}`
      },
      body: options.body
    });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok || !data?.ok) throw new Error(data?.message || `알림 API 오류 (${response.status})`);
    return data;
  }

  function itemHtml(item) {
    const meta = [item.businessDate, item.site, item.roomNo ? `${item.roomNo}호` : ''].filter(Boolean).join(' · ');
    return `<article class="nova-notification-item">
      <div class="nova-notification-item-top">
        <strong class="nova-notification-item-title">${escapeHtml(item.title || '알림')}</strong>
        <span class="nova-notification-item-time">${escapeHtml(item.createdAt || '')}</span>
      </div>
      ${item.message ? `<div class="nova-notification-item-message">${escapeHtml(item.message)}</div>` : ''}
      ${meta ? `<div class="nova-notification-item-meta">${escapeHtml(meta)}</div>` : ''}
    </article>`;
  }

  function renderPanel() {
    const body = byId('novaNotificationBody');
    const summary = byId('novaNotificationSummary');
    const clear = byId('novaNotificationClear');
    if (!body) return;
    summary.textContent = `보관 중 ${Math.max(0, Number(model.count || 0))}건`;
    body.innerHTML = model.items.length
      ? model.items.map(itemHtml).join('')
      : '<div class="nova-notification-empty">새 알림이 없습니다.</div>';
    clear.disabled = Number(model.count || 0) <= 0;
  }

  function closePanel() {
    byId('novaNotificationOverlay')?.remove();
  }

  async function openPanel() {
    if (!model.active) return;
    closePanel();
    const overlay = document.createElement('div');
    overlay.id = 'novaNotificationOverlay';
    overlay.className = 'nova-notification-overlay';
    overlay.innerHTML = `<section class="nova-notification-card" role="dialog" aria-modal="true" aria-label="알림">
      <div class="nova-notification-header"><strong>알림</strong><button id="novaNotificationClose" class="nova-notification-close" type="button">×</button></div>
      <div id="novaNotificationBody" class="nova-notification-body"><div id="novaNotificationSummary" class="nova-notification-summary">알림을 불러오는 중입니다.</div><div class="nova-notification-empty">불러오는 중…</div></div>
      <div class="nova-notification-footer"><button id="novaNotificationClear" class="nova-notification-clear" type="button">전체 지우기</button></div>
    </section>`;
    document.body.appendChild(overlay);
    byId('novaNotificationClose')?.addEventListener('click', closePanel);
    overlay.addEventListener('click', event => { if (event.target === overlay) closePanel(); });
    byId('novaNotificationClear')?.addEventListener('click', clearAll);
    await loadNotifications(true);
    renderPanel();
  }

  async function clearAll() {
    const count = Math.max(0, Number(model.count || 0));
    if (!count || !window.confirm(`알림 ${count}건을 모두 지울까요?`)) return;
    const button = byId('novaNotificationClear');
    if (button) { button.disabled = true; button.textContent = '지우는 중…'; }
    try {
      await apiFetch('/v1/notifications/clear', { method: 'POST', body: '{}' });
      model.items = [];
      model.count = 0;
      renderBadge();
      renderPanel();
    } catch (error) {
      console.error('[NOVA 알림] 전체삭제 실패', error);
      if (button) { button.disabled = false; button.textContent = '전체 지우기'; }
    }
  }

  async function loadNotifications(force = false) {
    if (!model.active || model.busy || !mainVisible()) return;
    if (!force && document.hidden) return;
    model.busy = true;
    try {
      const data = await apiFetch('/v1/notifications?limit=100');
      model.items = Array.isArray(data.notifications) ? data.notifications : [];
      model.count = Math.max(0, Number(data.count || 0));
      renderBadge();
      if (byId('novaNotificationOverlay')) renderPanel();
    } catch (error) {
      console.error('[NOVA 알림] 조회 실패', error);
    } finally {
      model.busy = false;
    }
  }

  function stopPolling() {
    if (model.timer) window.clearTimeout(model.timer);
    model.timer = null;
  }

  function schedulePolling(immediate = false) {
    stopPolling();
    if (!model.active) return;
    const run = async () => {
      if (!mainVisible() || localStorage.getItem('novaToken') !== model.token) {
        model.active = false;
        removeButton();
        return;
      }
      await loadNotifications();
      const base = document.hidden ? 15000 : 5000;
      const jitter = document.hidden ? 2000 : 1200;
      model.timer = window.setTimeout(run, base + Math.floor(Math.random() * jitter));
    };
    model.timer = window.setTimeout(run, immediate ? 0 : 1200);
  }

  async function bootstrapNotificationModule() {
    if (model.active || !mainVisible()) return;
    const token = localStorage.getItem('novaToken') || '';
    if (!token) return;
    try {
      const clientType = window.matchMedia('(max-width: 760px)').matches ? 'mobile' : 'desktop';
      const bootstrap = await gsCall('getBootstrap', token, clientType);
      const role = String(bootstrap?.user?.role || '').trim().toUpperCase();
      if (!bootstrap?.ok || !allowedRoles.has(role)) {
        model.active = false;
        model.role = role;
        removeButton();
        return;
      }
      const config = await gsCall('getNovaRealtimeClientConfig', token);
      const apiBase = String(config?.apiBase || '').replace(/\/+$/, '');
      if (!config?.ok || !config?.enabled || !apiBase) return;
      model.token = token;
      model.apiBase = apiBase;
      model.role = role;
      model.active = true;
      ensureButton();
      renderBadge();
      schedulePolling(true);
    } catch (error) {
      // 개인 알림은 참고기능입니다. 실패해도 NOVA 핵심화면에는 절대 영향을 주지 않습니다.
      console.error('[NOVA 알림] 독립 초기화 실패', error);
    }
  }

  function watchMainView() {
    const tryStart = () => {
      if (mainVisible()) {
        window.setTimeout(() => { void bootstrapNotificationModule(); }, 600);
      } else {
        stopPolling();
        model.active = false;
        model.token = '';
        model.apiBase = '';
        model.role = '';
        model.count = 0;
        model.items = [];
        removeButton();
        closePanel();
      }
    };
    const main = byId('mainView');
    if (main) new MutationObserver(tryStart).observe(main, { attributes: true, attributeFilter: ['class'] });
    document.addEventListener('visibilitychange', () => {
      if (model.active && !document.hidden) void loadNotifications(true);
    });
    tryStart();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', watchMainView, { once: true });
  } else {
    watchMainView();
  }
})();
</script>
''', encoding='utf-8')

index_check = index.read_text(encoding='utf-8')
notification_check = notification.read_text(encoding='utf-8')
checks = [
    "include_('NotificationClient')",
]
for marker in checks:
    if marker not in index_check:
        raise SystemExit(f'Index marker missing: {marker}')
for marker in [
    "const allowedRoles = new Set(['HOUSEMAN', 'ROOMMAID', 'QM'])",
    "getBootstrap",
    "getNovaRealtimeClientConfig",
    "/v1/notifications?limit=100",
    "/v1/notifications/clear",
    "MutationObserver",
    "개인 알림은 참고기능입니다"
]:
    if marker not in notification_check:
        raise SystemExit(f'Notification marker missing: {marker}')

# 핵심 Client는 이번 패치에서 절대 수정하지 않는다.
print('ISOLATED_NOTIFICATION_CLIENT_V89_OK')
