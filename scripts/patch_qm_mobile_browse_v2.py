from pathlib import Path
import sys

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
updated = text
marker = 'QM 추가탭 동·층 필터 + 안전 즉시점검'

if marker in updated:
    print('QM browse v2 patch already applied.')
    sys.exit(0)

# 1) 추가탭 전용 동·층 필터 영역만 삽입합니다.
old_shell = '''        <div id="qmBrowseTabs" class="mobile-filters" hidden></div>\n        <div id="mobileFilters" class="mobile-filters"></div>\n'''
new_shell = '''        <div id="qmBrowseTabs" class="mobile-filters" hidden></div>\n        <div id="qmBrowseLocationFilters" class="mobile-location-filters" hidden>\n          <label><span>동</span><select id="qmBrowseBuilding"><option value="">전체 동</option></select></label>\n          <label><span>층</span><select id="qmBrowseFloor"><option value="">전체 층</option></select></label>\n        </div>\n        <div id="mobileFilters" class="mobile-filters"></div>\n'''
if old_shell not in updated:
    print('ERROR: QM browse v2 shell anchor not found.', file=sys.stderr)
    sys.exit(20)
updated = updated.replace(old_shell, new_shell, 1)

# 2) 날짜/사업장 변경 시 추가탭 위치필터도 함께 초기화합니다.
old_reset = '''      state.mobile.qmBrowseData = null;\n      state.mobile.qmBrowseLimit = 50;\n      loadMobileSnapshot();\n'''
new_reset = '''      state.mobile.qmBrowseData = null;\n      state.mobile.qmBrowseLimit = 50;\n      state.mobile.qmBrowseBuilding = '';\n      state.mobile.qmBrowseFloor = '';\n      loadMobileSnapshot();\n'''
if updated.count(old_reset) != 2:
    print(f'ERROR: Expected 2 QM browse reset anchors, found {updated.count(old_reset)}.', file=sys.stderr)
    sys.exit(21)
updated = updated.replace(old_reset, new_reset, 2)

# 3) 전용 동·층 선택 이벤트는 클라이언트 배열만 다시 필터링합니다. 서버 재호출은 없습니다.
old_floor_listener = '''    $('mobileFloor').addEventListener('change', event => {\n      state.mobile.floor = event.target.value;\n      renderMobileSummary();\n      renderMobileList();\n    });\n    $('mobileSearch').addEventListener('input', event => {\n'''
new_floor_listener = '''    $('mobileFloor').addEventListener('change', event => {\n      state.mobile.floor = event.target.value;\n      renderMobileSummary();\n      renderMobileList();\n    });\n    $('qmBrowseBuilding').addEventListener('change', event => {\n      state.mobile.qmBrowseBuilding = event.target.value;\n      state.mobile.qmBrowseFloor = '';\n      state.mobile.qmBrowseLimit = 50;\n      renderQmBrowseLocationFilters_();\n      renderMobileList();\n    });\n    $('qmBrowseFloor').addEventListener('change', event => {\n      state.mobile.qmBrowseFloor = event.target.value;\n      state.mobile.qmBrowseLimit = 50;\n      renderMobileList();\n    });\n    $('mobileSearch').addEventListener('input', event => {\n'''
if old_floor_listener not in updated:
    print('ERROR: QM browse v2 floor listener anchor not found.', file=sys.stderr)
    sys.exit(22)
updated = updated.replace(old_floor_listener, new_floor_listener, 1)

# 4) 모바일 데이터 렌더 순서는 그대로 두고 추가탭 위치필터 렌더만 끼웁니다.
old_render_data = '''    renderMobileLocationFilters_();\n    renderQmBrowseTabs_();\n    renderMobileSummary();\n'''
new_render_data = '''    renderMobileLocationFilters_();\n    renderQmBrowseTabs_();\n    renderQmBrowseLocationFilters_();\n    renderMobileSummary();\n'''
if old_render_data not in updated:
    print('ERROR: QM browse v2 render anchor not found.', file=sys.stderr)
    sys.exit(23)
updated = updated.replace(old_render_data, new_render_data, 1)

# 5) 탭 변경 시 동·층 필터는 새 탭 기준으로 초기화합니다.
old_tab_change = '''      state.mobile.qmView = nextView;\n      state.mobile.qmBrowseLimit = 50;\n      renderQmBrowseTabs_();\n      renderMobileSummary();\n'''
new_tab_change = '''      state.mobile.qmView = nextView;\n      state.mobile.qmBrowseLimit = 50;\n      state.mobile.qmBrowseBuilding = '';\n      state.mobile.qmBrowseFloor = '';\n      renderQmBrowseTabs_();\n      renderQmBrowseLocationFilters_();\n      renderMobileSummary();\n'''
if old_tab_change not in updated:
    print('ERROR: QM browse v2 tab change anchor not found.', file=sys.stderr)
    sys.exit(24)
updated = updated.replace(old_tab_change, new_tab_change, 1)

# 6) 캐시/서버 응답 후 위치필터 옵션을 현재 목록으로 즉시 갱신합니다.
old_cached = '''    if (!options.force && cached?.key === key && Array.isArray(cached.rooms)) {\n      renderMobileSummary();\n      renderMobileList();\n      return;\n    }\n'''
new_cached = '''    if (!options.force && cached?.key === key && Array.isArray(cached.rooms)) {\n      renderQmBrowseLocationFilters_();\n      renderMobileSummary();\n      renderMobileList();\n      return;\n    }\n'''
if old_cached not in updated:
    print('ERROR: QM browse v2 cached render anchor not found.', file=sys.stderr)
    sys.exit(25)
updated = updated.replace(old_cached, new_cached, 1)

old_loaded = '''      renderMobileSummary();\n      renderMobileList();\n      setSyncStatus(`QM ${view === 'CLEANED' ? '당일 청소완료' : '공실'} 조회 · ${state.mobile.qmBrowseData.rooms.length}실`);\n'''
new_loaded = '''      renderQmBrowseLocationFilters_();\n      renderMobileSummary();\n      renderMobileList();\n      setSyncStatus(`QM ${view === 'CLEANED' ? '당일 청소완료' : '공실'} 조회 · ${state.mobile.qmBrowseData.rooms.length}실`);\n'''
if old_loaded not in updated:
    print('ERROR: QM browse v2 loaded render anchor not found.', file=sys.stderr)
    sys.exit(26)
updated = updated.replace(old_loaded, new_loaded, 1)

# 7) 위치필터는 최대 798실의 이미 로드된 배열에서만 계산합니다.
card_anchor = "  function renderQmBrowseRoomCard_(room, view) { // (QM 추가탭 조회전용 카드 · 기존 점검권한 변경 없음)\n"
if card_anchor not in updated:
    print('ERROR: QM browse v2 card anchor not found.', file=sys.stderr)
    sys.exit(27)
location_helper = r'''  function renderQmBrowseLocationFilters_() { // (QM 추가탭 동·층 클라이언트 필터 · 서버 재조회 없음)
    const panel = $('qmBrowseLocationFilters');
    const buildingSelect = $('qmBrowseBuilding');
    const floorSelect = $('qmBrowseFloor');
    if (!panel || !buildingSelect || !floorSelect) return;
    const role = String(state.mobile.data?.role || '').trim().toUpperCase();
    const view = qmMobileBrowseView_();
    const visible = role === 'QM' && view !== 'TARGETS';
    panel.hidden = !visible;
    if (!visible) return;

    const key = qmMobileBrowseKey_(view);
    const browse = state.mobile.qmBrowseData;
    const rooms = browse?.key === key && Array.isArray(browse.rooms) ? browse.rooms : [];
    const buildings = [...new Set(rooms.map(room => String(room.building || '').trim()).filter(Boolean))]
      .sort((a, b) => Number(a.replace(/\D/g, '')) - Number(b.replace(/\D/g, '')) || a.localeCompare(b, 'ko'));
    if (state.mobile.qmBrowseBuilding && !buildings.includes(state.mobile.qmBrowseBuilding)) state.mobile.qmBrowseBuilding = '';
    buildingSelect.innerHTML = '<option value="">전체 동</option>' + buildings.map(building => `<option value="${escapeAttr(building)}">${escapeHtml(building)}</option>`).join('');
    buildingSelect.value = state.mobile.qmBrowseBuilding || '';

    const floors = [...new Set(rooms
      .filter(room => !state.mobile.qmBrowseBuilding || String(room.building || '') === state.mobile.qmBrowseBuilding)
      .map(room => String(room.floor || '').trim()).filter(Boolean))]
      .sort((a, b) => Number(a) - Number(b) || a.localeCompare(b, 'ko'));
    if (state.mobile.qmBrowseFloor && !floors.includes(state.mobile.qmBrowseFloor)) state.mobile.qmBrowseFloor = '';
    floorSelect.innerHTML = '<option value="">전체 층</option>' + floors.map(floor => `<option value="${escapeAttr(floor)}">${escapeHtml(floor)}층</option>`).join('');
    floorSelect.value = state.mobile.qmBrowseFloor || '';
  }

'''
updated = updated.replace(card_anchor, location_helper + card_anchor, 1)

# 8) 추가탭 카드에 현재 QM 충돌상태를 반영한 점검버튼만 추가합니다.
old_card = r'''  function renderQmBrowseRoomCard_(room, view) { // (QM 추가탭 조회전용 카드 · 기존 점검권한 변경 없음)
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
new_card = r'''  function renderQmBrowseRoomCard_(room, view) { // (QM 추가탭 카드 · 안전 본인확보 후 기존 체크리스트 연결)
    const roomStatus = codeLabel_(state.mobile.data?.codes?.roomStatuses, room.roomStatus);
    const cleaningStatus = codeLabel_(state.mobile.data?.codes?.cleaningStatuses, room.cleaningStatus);
    const assignedNames = [room.roommaidName, room.secondaryRoommaidName].filter(Boolean).join(' · ') || '-';
    const qmName = String(room.qmName || '').trim();
    const qmNo = String(room.qmEmployeeNo || '').trim();
    const employeeNo = String(state.bootstrap?.user?.employeeNo || '').trim();
    const status = String(room.cleaningStatus || '').trim().toUpperCase();
    const operationBadges = [
      room.preassigned ? '<span class="mobile-operation-badge preassigned">선배정</span>' : '',
      room.vip ? '<span class="mobile-operation-badge vip">VIP</span>' : '',
      room.importantRoom ? '<span class="mobile-operation-badge important">중요</span>' : ''
    ].filter(Boolean).join('');
    const viewLabel = view === 'CLEANED' ? '당일 청소완료' : '공실';
    let actions = '';
    if (status === 'QM_COMPLETED') {
      actions = '<button type="button" disabled>점검완료</button>';
    } else if (qmNo && qmNo !== employeeNo) {
      actions = '<button type="button" disabled>다른 QM 배정</button>';
    } else if (status === 'QM_CHECKING' && qmNo === employeeNo) {
      actions = `<button type="button" class="primary" data-qm-browse-inspect="${escapeAttr(room.roomNo)}">점검 계속</button>`;
    } else if (['COMPLETED', 'QM_WAITING'].includes(status)) {
      actions = `<button type="button" class="primary" data-qm-browse-inspect="${escapeAttr(room.roomNo)}">점검 시작</button>`;
    }
    return `<article class="mobile-room-card qm-browse-inspection">
      <div class="mobile-card-top"><strong>${escapeHtml(room.roomNo)}</strong><span>${escapeHtml([room.building, room.floor ? `${room.floor}층` : ''].filter(Boolean).join(' · '))}</span></div>
      ${operationBadges ? `<div class="mobile-operation-badges">${operationBadges}</div>` : ''}
      <div class="mobile-room-status"><b>${escapeHtml(assignedNames)}</b><span>${escapeHtml(cleaningStatus || roomStatus)}</span></div>
      <div class="mobile-cleaning-type"><span>${escapeHtml(viewLabel)}</span>${qmName ? ` · QM ${escapeHtml(qmName)}` : ''}</div>
      ${actions ? `<div class="mobile-actions">${actions}</div>` : ''}
    </article>`;
  }

'''
if old_card not in updated:
    print('ERROR: QM browse v2 original card function not found.', file=sys.stderr)
    sys.exit(28)
updated = updated.replace(old_card, new_card, 1)

# 9) 목록 필터에 동·층 조건을 추가합니다. 렌더 50실 제한은 그대로 유지합니다.
old_filter = '''      const filtered = browse.rooms.filter(room => {\n        if (!query) return true;\n        return [room.roomNo, room.building, room.floor ? `${room.floor}층` : '', room.roomStatus, room.cleaningStatus, room.roommaidName, room.secondaryRoommaidName, room.qmName]\n          .join(' ').toLowerCase().includes(query);\n      });\n'''
new_filter = '''      const filtered = browse.rooms.filter(room => {\n        if (state.mobile.qmBrowseBuilding && String(room.building || '') !== state.mobile.qmBrowseBuilding) return false;\n        if (state.mobile.qmBrowseFloor && String(room.floor || '') !== state.mobile.qmBrowseFloor) return false;\n        if (!query) return true;\n        return [room.roomNo, room.building, room.floor ? `${room.floor}층` : '', room.roomStatus, room.cleaningStatus, room.roommaidName, room.secondaryRoommaidName, room.qmName]\n          .join(' ').toLowerCase().includes(query);\n      });\n'''
if old_filter not in updated:
    print('ERROR: QM browse v2 list filter anchor not found.', file=sys.stderr)
    sys.exit(29)
updated = updated.replace(old_filter, new_filter, 1)

# 10) 추가탭 점검시작은 단일 서버호출로 본인확보+QM_CHECKING+DB 단건동기화+기존 체크리스트를 준비합니다.
handle_anchor = "  async function handleMobileListClick(event) { // (모바일 카드 작업 처리)\n"
if handle_anchor not in updated:
    print('ERROR: QM browse v2 mobile click anchor not found.', file=sys.stderr)
    sys.exit(30)
start_helper = r'''  async function startQmBrowseInspection_(roomNo, button) { // (QM 추가탭 즉시점검 · 단일왕복 후 기존 체크리스트 재사용)
    const view = qmMobileBrowseView_();
    const key = qmMobileBrowseKey_(view);
    const browse = state.mobile.qmBrowseData;
    const room = browse?.key === key && Array.isArray(browse.rooms)
      ? browse.rooms.find(item => String(item.roomNo || '') === String(roomNo || ''))
      : null;
    if (!room) {
      showToast('점검할 객실을 다시 불러와 주세요.');
      return;
    }

    const originalText = button?.textContent || '';
    if (button) {
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.textContent = '시작 중…';
    }
    try {
      const result = await callServer('startQmMobileBrowseInspection', state.token, {
        businessDate: state.mobile.businessDate || state.bootstrap.app.businessDate,
        site: room.site || state.mobile.site,
        roomNo: room.roomNo,
        rowNumber: Number(room.rowNumber || 0),
        view
      });
      if (!result?.ok) throw new Error(result?.message || 'QM 점검을 시작하지 못했습니다.');
      const checklist = result.checklist || state.mobile.data?.qmChecklist || {};
      if (!(checklist.items || []).length) throw new Error('QM 체크리스트를 불러오지 못했습니다.');

      const confirmed = Object.assign({}, room, result.room || {}, {
        rowNumber: Number(result.room?.rowNumber || room.rowNumber || 0),
        businessDate: state.mobile.businessDate || room.businessDate,
        site: String(result.room?.site || room.site || state.mobile.site || ''),
        roomNo: String(room.roomNo || ''),
        qmEmployeeNo: String(state.bootstrap?.user?.employeeNo || ''),
        qmName: String(state.bootstrap?.user?.name || ''),
        cleaningStatus: 'QM_CHECKING',
        version: Number(result.room?.version || result.version || 0)
      });
      const targetRooms = state.mobile.data.rooms || (state.mobile.data.rooms = []);
      const existingIndex = targetRooms.findIndex(item => String(item.site || '') === confirmed.site && String(item.roomNo || '') === confirmed.roomNo);
      if (existingIndex >= 0) targetRooms[existingIndex] = Object.assign({}, targetRooms[existingIndex], confirmed);
      else targetRooms.push(confirmed);
      state.mobile.data.qmChecklist = checklist;
      state.qmChecklist.activeInspection = {
        roomNo: confirmed.roomNo,
        checklist,
        draft: result.draft,
        roomVersion: Number(confirmed.version || 0),
        sheetExpectedVersion: 0,
        localDirty: false
      };

      // 시작 후에는 기존 점검대상 흐름으로 복귀시켜 제출/재정비/완료 로직을 그대로 사용합니다.
      state.mobile.qmView = 'TARGETS';
      state.mobile.qmBrowseData = null;
      state.mobile.qmBrowseBuilding = '';
      state.mobile.qmBrowseFloor = '';
      state.mobile.qmBrowseLimit = 50;
      renderQmBrowseTabs_();
      renderQmBrowseLocationFilters_();
      renderMobileSummary();
      renderMobileFilters();
      renderMobileList();
      openQmInspectionModal_();
      setSyncStatus(`${confirmed.roomNo}호 QM 점검 시작`);
      void loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 추가탭 점검시작 후 화면갱신 실패:', error));
    } catch (error) {
      showToast(error?.message || 'QM 점검 시작 오류');
    } finally {
      if (button && button.isConnected) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
        button.textContent = originalText || '점검 시작';
      }
    }
  }

'''
updated = updated.replace(handle_anchor, start_helper + handle_anchor, 1)

# 11) 기존 모바일 클릭 처리보다 먼저 추가탭 점검버튼만 분기합니다.
old_handle_head = '''  async function handleMobileListClick(event) { // (모바일 카드 작업 처리)\n    const orderButton = event.target.closest('[data-order-action]');\n'''
new_handle_head = '''  async function handleMobileListClick(event) { // (모바일 카드 작업 처리)\n    const qmBrowseButton = event.target.closest('[data-qm-browse-inspect]');\n    if (qmBrowseButton) return startQmBrowseInspection_(qmBrowseButton.dataset.qmBrowseInspect, qmBrowseButton);\n    const orderButton = event.target.closest('[data-order-action]');\n'''
if old_handle_head not in updated:
    print('ERROR: QM browse v2 handle head not found.', file=sys.stderr)
    sys.exit(31)
updated = updated.replace(old_handle_head, new_handle_head, 1)

# 최종 표식: 기존 기능을 건드리지 않고 QM 추가탭에서만 실행됩니다.
updated = updated.replace(
    "  function qmMobileBrowseView_() { // (QM 추가조회 탭 · 기존 점검대상 화면 보존)\n",
    "  function qmMobileBrowseView_() { // (QM 추가조회 탭 · 기존 점검대상 화면 보존 · QM 추가탭 동·층 필터 + 안전 즉시점검)\n",
    1,
)

path.write_text(updated, encoding='utf-8')
print('Applied QM browse v2 location filters and safe inspection flow.')
