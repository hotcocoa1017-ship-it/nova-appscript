from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
original = text
marker = 'MOBILE_MY_HOUSEMAN_ORDERS_V1'

# 1) Shared read-only loader/render helpers, inserted before QM view helpers.
anchor = "  function qmMobileBrowseView_() { // (QM 추가조회 탭 · 기존 점검대상 화면 보존 · QM 추가탭 동·층 필터 + 안전 즉시점검)\n"
helper = r'''  // MOBILE_MY_HOUSEMAN_ORDERS_V1 · ROOMMAID/QM 본인 등록 하우스맨 오더 조회 전용
  function mobileMyRequestsKey_() {
    return [
      state.mobile.businessDate || state.bootstrap.app.businessDate || '',
      state.mobile.site || ''
    ].join('|');
  }

  function mobileMyRequestStatusLabel_(order) {
    const code = String(order?.statusCode || '').trim().toUpperCase();
    const label = codeLabel_(state.mobile.data?.codes?.orderStatuses, code);
    if (label && label !== code) return label;
    const fallback = {
      REGISTERED: '접수대기', ASSIGNED: '배정', ACCEPTED: '접수',
      PROCESSING: '처리중', COMPLETED: '완료', UNABLE: '처리불가'
    };
    return fallback[code] || code || '-';
  }

  function mobileMyRequestTime_(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
  }

  async function novaMobileMyRequestsDb_(businessDate, site) {
    if (!novaRealtimeIsEnabled_()) throw new Error('실시간 DB 연결이 준비되지 않았습니다.');
    const auth = await novaRealtimeGetAuth_();
    if (!auth?.token || !auth?.supabaseUrl || !auth?.publishableKey) {
      throw new Error('내 요청 조회 인증정보를 준비하지 못했습니다.');
    }
    const endpoint = `${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_mobile_my_houseman_orders_v1`;
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${String(auth.token || '')}`,
        'apikey': String(auth.publishableKey || '')
      },
      body: JSON.stringify({
        p_business_date: String(businessDate || '').trim(),
        p_site: String(site || '').trim()
      })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data?.ok) {
      const error = new Error(data?.message || data?.details || `내 요청 조회 오류 (${response.status})`);
      error.code = String(data?.code || '').trim();
      throw error;
    }
    return data;
  }

  function renderMobileMyRequestCard_(order) {
    const statusCode = String(order?.statusCode || '').trim().toUpperCase();
    const statusLabel = mobileMyRequestStatusLabel_(order);
    const registeredTime = mobileMyRequestTime_(order?.registeredAt);
    const completedTime = mobileMyRequestTime_(order?.completedAt);
    const assignedName = String(order?.processorName || order?.assignedName || '').trim();
    const unableReason = String(order?.unableReason || '').trim();
    return `<article class="mobile-task-card" data-mobile-my-request-id="${escapeAttr(String(order?.orderId || ''))}">
      <div class="mobile-card-top"><strong>${escapeHtml(String(order?.roomNo || '공용'))}</strong><span class="status-chip status-${escapeAttr(statusCode)}">${escapeHtml(statusLabel)}</span></div>
      <div class="mobile-task-title">${escapeHtml(String(order?.itemSummary || '-'))}</div>
      <div class="mobile-task-meta"><span>${escapeHtml(String(order?.part || '-'))}</span><span>${registeredTime ? `등록 ${escapeHtml(registeredTime)}` : ''}</span></div>
      ${order?.note ? `<p>${escapeHtml(String(order.note))}</p>` : ''}
      ${assignedName ? `<div class="mobile-task-meta"><span>담당 ${escapeHtml(assignedName)}</span><span>${completedTime ? `완료 ${escapeHtml(completedTime)}` : ''}</span></div>` : (completedTime ? `<div class="mobile-task-meta"><span></span><span>완료 ${escapeHtml(completedTime)}</span></div>` : '')}
      ${statusCode === 'UNABLE' && unableReason ? `<div class="mobile-unable-reason"><strong>처리불가 사유</strong><span>${escapeHtml(unableReason)}</span></div>` : ''}
    </article>`;
  }

  function renderMobileMyRequestsSummary_() {
    const summaryEl = $('mobileSummary');
    if (!summaryEl) return;
    const key = mobileMyRequestsKey_();
    const data = state.mobile.myRequestData;
    const orders = data?.key === key && Array.isArray(data.orders) ? data.orders : [];
    const done = orders.filter(order => ['COMPLETED', 'UNABLE'].includes(String(order?.statusCode || '').trim().toUpperCase())).length;
    const active = Math.max(0, orders.length - done);
    summaryEl.innerHTML = [
      ['내 요청', orders.length], ['진행', active], ['완료', done]
    ].map(([label, value]) => `<div class="mobile-summary-card"><span>${escapeHtml(label)}</span><strong>${Number(value || 0)}</strong></div>`).join('');
  }

  async function loadMobileMyRequests_(options = {}) {
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    if (!['ROOMMAID', 'QM'].includes(role)) return;
    const businessDate = state.mobile.businessDate || state.bootstrap.app.businessDate || '';
    const site = state.mobile.site || '';
    if (!businessDate || !site) return;
    const key = mobileMyRequestsKey_();
    if (!options.force && state.mobile.myRequestData?.key === key && Array.isArray(state.mobile.myRequestData.orders)) {
      renderMobileMyRequestsSummary_();
      renderMobileList();
      return;
    }
    if (state.mobile.myRequestsLoading) return;
    state.mobile.myRequestsLoading = true;
    try {
      const result = await novaMobileMyRequestsDb_(businessDate, site);
      state.mobile.myRequestData = {
        key,
        orders: Array.isArray(result.orders) ? result.orders : [],
        serverTime: result.serverTime || ''
      };
      renderMobileMyRequestsSummary_();
      renderMobileList();
      setSyncStatus(`내 요청 ${state.mobile.myRequestData.orders.length}건 · 최신순`);
    } catch (error) {
      const container = $('mobileList');
      if (container) container.innerHTML = `<div class="mobile-empty">${escapeHtml(error?.message || '내 요청을 불러오지 못했습니다.')}</div>`;
      setSyncStatus(`내 요청 조회 오류 · ${error?.message || '조회 실패'}`);
    } finally {
      state.mobile.myRequestsLoading = false;
    }
  }

  function qmMobileBrowseView_() { // (QM 추가조회 탭 · 기존 점검대상 화면 보존 · QM 추가탭 동·층 필터 + 안전 즉시점검)
'''
if marker not in text:
    if anchor not in text:
        raise SystemExit('ERROR: qmMobileBrowseView anchor not found')
    text = text.replace(anchor, helper, 1)

# 2) QM: add MY_REQUESTS as a fourth top tab.
old_view = "return ['TARGETS', 'CLEANED', 'VACANT'].includes(view) ? view : 'TARGETS';"
new_view = "return ['TARGETS', 'CLEANED', 'VACANT', 'MY_REQUESTS'].includes(view) ? view : 'TARGETS';"
if new_view not in text:
    if old_view not in text:
        raise SystemExit('ERROR: QM view allowed-list anchor not found')
    text = text.replace(old_view, new_view, 1)

old_tabs = """      ['TARGETS', '점검대상'],\n      ['CLEANED', '당일 청소완료'],\n      ['VACANT', '공실']\n"""
new_tabs = """      ['TARGETS', '점검대상'],\n      ['CLEANED', '당일 청소완료'],\n      ['VACANT', '공실'],\n      ['MY_REQUESTS', '내 요청']\n"""
if new_tabs not in text:
    if old_tabs not in text:
        raise SystemExit('ERROR: QM tabs anchor not found')
    text = text.replace(old_tabs, new_tabs, 1)

old_tab_action = """      if (nextView === 'TARGETS') {\n        renderMobileList();\n        return;\n      }\n      await loadQmMobileBrowse_();\n"""
new_tab_action = """      if (nextView === 'TARGETS') {\n        renderMobileList();\n        return;\n      }\n      if (nextView === 'MY_REQUESTS') {\n        state.mobile.myRequestData = null;\n        await loadMobileMyRequests_({ force: true });\n        return;\n      }\n      await loadQmMobileBrowse_();\n"""
if new_tab_action not in text:
    if old_tab_action not in text:
        raise SystemExit('ERROR: QM tab action anchor not found')
    text = text.replace(old_tab_action, new_tab_action, 1)

# 3) QM location filters must stay hidden on My Requests.
old_loc = "const visible = role === 'QM' && view !== 'TARGETS';"
new_loc = "const visible = role === 'QM' && !['TARGETS', 'MY_REQUESTS'].includes(view);"
if new_loc not in text:
    if old_loc not in text:
        raise SystemExit('ERROR: QM location visibility anchor not found')
    text = text.replace(old_loc, new_loc, 1)

# 4) Summary: My Requests summary takes precedence for ROOMMAID/QM.
summary_anchor = """    const role = data?.role;\n    if (role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n"""
summary_new = """    const role = data?.role;\n    const myRequestsView = (role === 'ROOMMAID' && state.mobile.filter === 'MY_REQUESTS')\n      || (role === 'QM' && qmMobileBrowseView_() === 'MY_REQUESTS');\n    if (myRequestsView) {\n      renderMobileMyRequestsSummary_();\n      return;\n    }\n    if (role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n"""
if summary_new not in text:
    if summary_anchor not in text:
        raise SystemExit('ERROR: mobile summary anchor not found')
    text = text.replace(summary_anchor, summary_new, 1)

# 5) ROOMMAID: add My Requests to its filter/tabs row only.
old_filters = """    const filters = role === 'PUBLIC'\n      ? [['DELAYED', '퇴실지연'], ['DUE_OUT', '퇴실예정'], ['CHECKED_OUT', '퇴실'], ['ALL', '전체']]\n      : role === 'HOUSEMAN'\n        ? [['ACTIVE', '진행'], ['IMPORTANT', '중요·인계'], ['DONE', '완료'], ['ALL', '전체']]\n        : [['ACTIVE', '진행'], ['DONE', '완료'], ['ALL', '전체']];\n"""
new_filters = """    const filters = role === 'PUBLIC'\n      ? [['DELAYED', '퇴실지연'], ['DUE_OUT', '퇴실예정'], ['CHECKED_OUT', '퇴실'], ['ALL', '전체']]\n      : role === 'HOUSEMAN'\n        ? [['ACTIVE', '진행'], ['IMPORTANT', '중요·인계'], ['DONE', '완료'], ['ALL', '전체']]\n        : role === 'ROOMMAID'\n          ? [['ACTIVE', '진행'], ['DONE', '완료'], ['ALL', '전체'], ['MY_REQUESTS', '내 요청']]\n          : [['ACTIVE', '진행'], ['DONE', '완료'], ['ALL', '전체']];\n"""
if new_filters not in text:
    if old_filters not in text:
        raise SystemExit('ERROR: mobile filters anchor not found')
    text = text.replace(old_filters, new_filters, 1)

old_filter_click = """      saveMobileViewPreference_(); // MOBILE_VIEW_STATE_PERSIST_V2\n      renderMobileFilters();\n      renderMobileList();\n    }));\n"""
new_filter_click = """      saveMobileViewPreference_(); // MOBILE_VIEW_STATE_PERSIST_V2\n      renderMobileFilters();\n      renderMobileList();\n      if (role === 'ROOMMAID' && state.mobile.filter === 'MY_REQUESTS') {\n        state.mobile.myRequestData = null;\n        void loadMobileMyRequests_({ force: true });\n      }\n    }));\n"""
if new_filter_click not in text:
    # Make sure this replacement hits renderMobileFilters, not another handler: use occurrence nearest filters function.
    pos = text.find("  function renderMobileFilters()")
    if pos < 0:
        raise SystemExit('ERROR: renderMobileFilters not found')
    end = text.find("\n  function renderMobileList()", pos)
    seg = text[pos:end]
    if old_filter_click not in seg:
        raise SystemExit('ERROR: mobile filter click anchor not found')
    seg = seg.replace(old_filter_click, new_filter_click, 1)
    text = text[:pos] + seg + text[end:]

# 6) List: My Requests is rendered read-only before QM browse/normal room paths.
list_anchor = """    const query = state.mobile.search.toLowerCase();\n    if (data.role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n"""
list_new = """    const query = state.mobile.search.toLowerCase();\n    const myRequestsView = (data.role === 'ROOMMAID' && state.mobile.filter === 'MY_REQUESTS')\n      || (data.role === 'QM' && qmMobileBrowseView_() === 'MY_REQUESTS');\n    if (myRequestsView) {\n      const key = mobileMyRequestsKey_();\n      const requestData = state.mobile.myRequestData;\n      if (!requestData || requestData.key !== key || !Array.isArray(requestData.orders)) {\n        container.innerHTML = '<div class=\"mobile-loading\">내 요청을 불러오고 있습니다.</div>';\n        if (!state.mobile.myRequestsLoading) void loadMobileMyRequests_();\n        return;\n      }\n      const orders = requestData.orders.filter(order => {\n        if (!query) return true;\n        return [order.roomNo, order.part, order.itemSummary, order.note, order.assignedName, order.processorName, mobileMyRequestStatusLabel_(order)]\n          .join(' ').toLowerCase().includes(query);\n      });\n      container.innerHTML = orders.length\n        ? orders.map(renderMobileMyRequestCard_).join('')\n        : '<div class=\"mobile-empty\">선택한 업무일자에 등록한 하우스맨 요청이 없습니다.</div>';\n      return;\n    }\n    if (data.role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n"""
if list_new not in text:
    if list_anchor not in text:
        raise SystemExit('ERROR: renderMobileList anchor not found')
    text = text.replace(list_anchor, list_new, 1)

required = [
  'MOBILE_MY_HOUSEMAN_ORDERS_V1',
  'nova_mobile_my_houseman_orders_v1',
  "['MY_REQUESTS', '내 요청']",
  "['ACTIVE', '진행'], ['DONE', '완료'], ['ALL', '전체'], ['MY_REQUESTS', '내 요청']",
  'function renderMobileMyRequestCard_',
  'function loadMobileMyRequests_',
  "qmMobileBrowseView_() === 'MY_REQUESTS'",
  "state.mobile.filter === 'MY_REQUESTS'"
]
for needle in required:
    if needle not in text:
        raise SystemExit(f'ERROR: required marker missing: {needle}')

if text == original:
    print('MOBILE_MY_HOUSEMAN_ORDERS_V1 already applied; no source change needed.')
else:
    path.write_text(text, encoding='utf-8')
    print('Applied MOBILE_MY_HOUSEMAN_ORDERS_V1 Client patch.')
