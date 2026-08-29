from pathlib import Path
import sys

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
updated = text
changed = False
marker = 'QM 추가조회 탭 · 기존 점검대상 화면 보존'

if marker in updated:
    print('QM mobile browse tabs already applied.')
    sys.exit(0)

# 1) QM 전용 탭 컨테이너만 추가합니다. 다른 직무에서는 hidden 상태입니다.
old_shell = '''        <div id=\"mobileShiftInfo\" class=\"mobile-shift-info\"></div>\n        <div id=\"mobileSummary\" class=\"mobile-summary\"></div>\n        <div id=\"mobileFilters\" class=\"mobile-filters\"></div>\n'''
new_shell = '''        <div id=\"mobileShiftInfo\" class=\"mobile-shift-info\"></div>\n        <div id=\"mobileSummary\" class=\"mobile-summary\"></div>\n        <div id=\"qmBrowseTabs\" class=\"mobile-filters\" hidden></div>\n        <div id=\"mobileFilters\" class=\"mobile-filters\"></div>\n'''
if old_shell not in updated:
    print('ERROR: QM browse shell anchor not found.', file=sys.stderr)
    sys.exit(10)
updated = updated.replace(old_shell, new_shell, 1)
changed = True

# 2) 날짜/사업장 변경 시 추가조회 캐시만 초기화합니다.
old_date = '''      state.mobile.floor = '';\n      state.mobile.version = 0;\n      loadMobileSnapshot();\n'''
new_date = '''      state.mobile.floor = '';\n      state.mobile.version = 0;\n      state.mobile.qmView = 'TARGETS';\n      state.mobile.qmBrowseData = null;\n      state.mobile.qmBrowseLimit = 50;\n      loadMobileSnapshot();\n'''
if updated.count(old_date) < 2:
    print('ERROR: QM browse date/site reset anchors not found twice.', file=sys.stderr)
    sys.exit(11)
updated = updated.replace(old_date, new_date, 2)

# 3) 새로고침은 기존 스냅샷을 그대로 갱신하고, 추가탭이 열려 있을 때만 그 탭을 다시 조회합니다.
old_sync = "    $('mobileSyncButton').addEventListener('click', () => loadMobileSnapshot({ force: true }));\n"
new_sync = '''    $('mobileSyncButton').addEventListener('click', async () => {\n      await loadMobileSnapshot({ force: true });\n      if (state.mobile.data?.role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n        await loadQmMobileBrowse_({ force: true });\n      }\n    });\n'''
if old_sync not in updated:
    print('ERROR: QM browse mobile sync anchor not found.', file=sys.stderr)
    sys.exit(12)
updated = updated.replace(old_sync, new_sync, 1)

# 4) 기존 모바일 렌더 순서를 유지하며 QM 탭 렌더만 끼웁니다.
old_render_data = '''    renderMobileLocationFilters_();\n    renderMobileSummary();\n    renderMobileFilters();\n    renderMobileList();\n'''
new_render_data = '''    renderMobileLocationFilters_();\n    renderQmBrowseTabs_();\n    renderMobileSummary();\n    renderMobileFilters();\n    renderMobileList();\n'''
if old_render_data not in updated:
    print('ERROR: QM browse renderMobileData anchor not found.', file=sys.stderr)
    sys.exit(13)
updated = updated.replace(old_render_data, new_render_data, 1)

# 5) QM 전용 추가조회 함수. 기본 TARGETS에서는 기존 데이터/필터/액션을 그대로 사용합니다.
anchor = "  function renderMobileSummary() { // (직무별 모바일 요약)\n"
if anchor not in updated:
    print('ERROR: QM browse summary function anchor not found.', file=sys.stderr)
    sys.exit(14)
helpers = r'''  function qmMobileBrowseView_() { // (QM 추가조회 탭 · 기존 점검대상 화면 보존)
    const role = String(state.mobile.data?.role || '').trim().toUpperCase();
    if (role !== 'QM') return 'TARGETS';
    const view = String(state.mobile.qmView || 'TARGETS').trim().toUpperCase();
    return ['TARGETS', 'CLEANED', 'VACANT'].includes(view) ? view : 'TARGETS';
  }

  function qmMobileBrowseKey_(view) { // (QM 추가조회 선택범위 캐시키)
    return [
      state.mobile.businessDate || state.bootstrap.app.businessDate || '',
      state.mobile.site || '',
      String(view || qmMobileBrowseView_()).toUpperCase()
    ].join('|');
  }

  function renderQmBrowseTabs_() { // (QM 점검대상·당일청소완료·공실 탭)
    const panel = $('qmBrowseTabs');
    if (!panel) return;
    const isQm = String(state.mobile.data?.role || '').trim().toUpperCase() === 'QM';
    panel.hidden = !isQm;
    if (!isQm) {
      panel.innerHTML = '';
      return;
    }
    const view = qmMobileBrowseView_();
    const tabs = [
      ['TARGETS', '점검대상'],
      ['CLEANED', '당일 청소완료'],
      ['VACANT', '공실']
    ];
    panel.innerHTML = tabs.map(([code, label]) => `<button type="button" class="mobile-filter${view === code ? ' active' : ''}" data-qm-browse-view="${escapeAttr(code)}">${escapeHtml(label)}</button>`).join('');
    panel.querySelectorAll('[data-qm-browse-view]').forEach(button => button.addEventListener('click', async () => {
      const nextView = String(button.dataset.qmBrowseView || 'TARGETS').toUpperCase();
      if (nextView === qmMobileBrowseView_()) return;
      state.mobile.qmView = nextView;
      state.mobile.qmBrowseLimit = 50;
      renderQmBrowseTabs_();
      renderMobileSummary();
      renderMobileFilters();
      if (nextView === 'TARGETS') {
        renderMobileList();
        return;
      }
      await loadQmMobileBrowse_();
    }));
  }

  async function loadQmMobileBrowse_(options = {}) { // (QM 추가목록 탭 선택 시에만 지연조회)
    if (String(state.mobile.data?.role || '').trim().toUpperCase() !== 'QM') return;
    const view = qmMobileBrowseView_();
    if (view === 'TARGETS') return;
    const key = qmMobileBrowseKey_(view);
    const cached = state.mobile.qmBrowseData;
    if (!options.force && cached?.key === key && Array.isArray(cached.rooms)) {
      renderMobileSummary();
      renderMobileList();
      return;
    }
    const container = $('mobileList');
    if (container) container.innerHTML = '<div class="mobile-loading">객실을 불러오고 있습니다.</div>';
    try {
      const result = await callServer('getQmMobileBrowseRooms', state.token, {
        businessDate: state.mobile.businessDate || state.bootstrap.app.businessDate,
        site: state.mobile.site,
        view
      });
      if (!result?.ok) throw new Error(result?.message || 'QM 객실목록을 불러오지 못했습니다.');
      if (view !== qmMobileBrowseView_()) return;
      state.mobile.qmBrowseData = {
        key,
        view,
        rooms: Array.isArray(result.rooms) ? result.rooms : [],
        summary: result.summary || {},
        serverTime: result.serverTime || ''
      };
      renderMobileSummary();
      renderMobileList();
      setSyncStatus(`QM ${view === 'CLEANED' ? '당일 청소완료' : '공실'} 조회 · ${state.mobile.qmBrowseData.rooms.length}실`);
    } catch (error) {
      if (container) container.innerHTML = `<div class="mobile-empty">${escapeHtml(error?.message || 'QM 객실목록을 불러오지 못했습니다.')}</div>`;
      setSyncStatus(`QM 추가조회 오류 · ${error?.message || '조회 실패'}`);
    }
  }

  function renderQmBrowseRoomCard_(room, view) { // (QM 추가탭 조회전용 카드 · 기존 점검권한 변경 없음)
    const roomStatus = codeLabel_(state.mobile.data?.codes?.roomStatuses, room.roomStatus);
    const cleaningStatus = codeLabel_(state.mobile.data?.codes?.cleaningStatuses, room.cleaningStatus);
    const assignedNames = [room.roommaidName, room.secondaryRoommaidName].filter(Boolean).join(' · ') || '-';
    const qmName = String(room.qmName || '').trim();
    const operationBadges = [
      room.preassigned ? '<span class="mobile-operation-badge preassigned">선배정</span>' : '',
      room.vip ? '<span class="mobile-operation-badge vip">VIP</span>' : '',
      room.importantRoom ? '<span class="mobile-operation-badge important">중요</span>' : ''
    ].filter(Boolean).join('');
    const viewLabel = view === 'CLEANED' ? '당일 청소완료' : '공실';
    return `<article class="mobile-room-card qm-browse-readonly">
      <div class="mobile-card-top"><strong>${escapeHtml(room.roomNo)}</strong><span>${escapeHtml([room.building, room.floor ? `${room.floor}층` : ''].filter(Boolean).join(' · '))}</span></div>
      ${operationBadges ? `<div class="mobile-operation-badges">${operationBadges}</div>` : ''}
      <div class="mobile-room-status"><b>${escapeHtml(assignedNames)}</b><span>${escapeHtml(cleaningStatus || roomStatus)}</span></div>
      <div class="mobile-cleaning-type"><span>${escapeHtml(viewLabel)}</span>${qmName ? ` · QM ${escapeHtml(qmName)}` : ''}</div>
    </article>`;
  }

'''
updated = updated.replace(anchor, helpers + anchor, 1)

# 6) 추가탭에서는 요약만 해당 목록 수량으로 표시합니다. TARGETS는 기존 요약 그대로입니다.
old_summary_head = '''  function renderMobileSummary() { // (직무별 모바일 요약)\n    const data = state.mobile.data;\n    const summary = data?.summary || {};\n    const role = data?.role;\n'''
new_summary_head = '''  function renderMobileSummary() { // (직무별 모바일 요약)\n    const data = state.mobile.data;\n    const summary = data?.summary || {};\n    const role = data?.role;\n    if (role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n      const view = qmMobileBrowseView_();\n      const browse = state.mobile.qmBrowseData;\n      const key = qmMobileBrowseKey_(view);\n      const count = browse?.key === key && Array.isArray(browse.rooms) ? browse.rooms.length : 0;\n      const label = view === 'CLEANED' ? '당일 청소완료' : '공실';\n      $('mobileSummary').innerHTML = `<div class=\"mobile-summary-card\"><span>${escapeHtml(label)}</span><strong>${count}</strong></div>`;\n      return;\n    }\n'''
if old_summary_head not in updated:
    print('ERROR: QM browse summary head anchor not found.', file=sys.stderr)
    sys.exit(15)
updated = updated.replace(old_summary_head, new_summary_head, 1)

# 7) 기존 ACTIVE/DONE/ALL 필터는 점검대상 탭에서 그대로 보존합니다.
old_filters_head = '''  function renderMobileFilters() { // (직무별 모바일 필터)\n    const role = state.mobile.data?.role;\n'''
new_filters_head = '''  function renderMobileFilters() { // (직무별 모바일 필터)\n    const role = state.mobile.data?.role;\n    const filterPanel = $('mobileFilters');\n    if (role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n      if (filterPanel) { filterPanel.hidden = true; filterPanel.innerHTML = ''; }\n      return;\n    }\n    if (filterPanel) filterPanel.hidden = false;\n'''
if old_filters_head not in updated:
    print('ERROR: QM browse filters head anchor not found.', file=sys.stderr)
    sys.exit(16)
updated = updated.replace(old_filters_head, new_filters_head, 1)

# 8) 추가탭은 50실 단위 렌더링으로 모바일 DOM 부하를 제한합니다.
old_list_head = '''  function renderMobileList() { // (직무별 모바일 카드 목록)\n    const data = state.mobile.data;\n    const container = $('mobileList');\n    if (!data || !container) return;\n    const query = state.mobile.search.toLowerCase();\n'''
new_list_head = '''  function renderMobileList() { // (직무별 모바일 카드 목록)\n    const data = state.mobile.data;\n    const container = $('mobileList');\n    if (!data || !container) return;\n    const query = state.mobile.search.toLowerCase();\n    if (data.role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n      const view = qmMobileBrowseView_();\n      const key = qmMobileBrowseKey_(view);\n      const browse = state.mobile.qmBrowseData;\n      if (!browse || browse.key !== key || !Array.isArray(browse.rooms)) {\n        container.innerHTML = '<div class=\"mobile-loading\">객실을 불러오고 있습니다.</div>';\n        return;\n      }\n      const filtered = browse.rooms.filter(room => {\n        if (!query) return true;\n        return [room.roomNo, room.building, room.floor ? `${room.floor}층` : '', room.roomStatus, room.cleaningStatus, room.roommaidName, room.secondaryRoommaidName, room.qmName]\n          .join(' ').toLowerCase().includes(query);\n      });\n      const limit = Math.max(50, Number(state.mobile.qmBrowseLimit || 50));\n      const visible = filtered.slice(0, limit);\n      const remaining = Math.max(0, filtered.length - visible.length);\n      container.innerHTML = visible.length\n        ? visible.map(room => renderQmBrowseRoomCard_(room, view)).join('') + (remaining ? `<button type=\"button\" class=\"secondary-button\" data-qm-browse-more>더 보기 · ${remaining}실 남음</button>` : '')\n        : '<div class=\"mobile-empty\">표시할 객실이 없습니다.</div>';\n      const moreButton = container.querySelector('[data-qm-browse-more]');\n      if (moreButton) moreButton.addEventListener('click', () => {\n        state.mobile.qmBrowseLimit = limit + 50;\n        renderMobileList();\n      });\n      return;\n    }\n'''
if old_list_head not in updated:
    print('ERROR: QM browse list head anchor not found.', file=sys.stderr)
    sys.exit(17)
updated = updated.replace(old_list_head, new_list_head, 1)

if changed or updated != text:
    path.write_text(updated, encoding='utf-8')
    print('Applied QM lazy browse tabs to Client.html.')
else:
    print('QM mobile browse tabs already applied.')
