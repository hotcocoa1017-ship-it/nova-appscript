from pathlib import Path
import sys

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
updated = text
marker = 'MOBILE_VIEW_STATE_PERSIST_V2'

if marker in updated:
    print('Mobile full view state persistence V2 already applied.')
    sys.exit(0)

# 1) 사용자/역할별 현재 모바일 화면 상태(탭·필터·검색)를 저장/복원합니다.
anchor = "  function mobileLocationPreferenceKey_(scope, view) { // (사용자·역할·업무일자·사업장별 동·층 저장키)\n"
if anchor not in updated:
    print('ERROR: mobile location preference anchor not found.', file=sys.stderr)
    sys.exit(20)

helpers = r'''  // MOBILE_VIEW_STATE_PERSIST_V2
  function mobileViewPreferenceKey_() { // (사용자·역할별 현재 모바일 화면상태 저장키)
    const employeeNo = String(state.bootstrap?.user?.employeeNo || '').trim() || 'ANON';
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase() || 'UNKNOWN';
    return `novaMobileView:${employeeNo}:${role}`;
  }

  function readMobileViewPreference_() { // (현재 탭·필터·검색 안전조회)
    try {
      const parsed = JSON.parse(localStorage.getItem(mobileViewPreferenceKey_()) || 'null');
      if (!parsed || typeof parsed !== 'object') return null;
      return {
        filter: String(parsed.filter || '').trim().toUpperCase(),
        search: String(parsed.search || ''),
        qmView: String(parsed.qmView || '').trim().toUpperCase()
      };
    } catch (ignore) {
      return null;
    }
  }

  function restoreMobileViewPreference_() { // (새로고침 후 현재 모바일 화면상태 복원)
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    if (!role) return;
    const saved = readMobileViewPreference_();
    if (!saved) return;
    if (saved.filter) state.mobile.filter = saved.filter;
    state.mobile.search = saved.search;
    if (role === 'QM' && ['TARGETS', 'CLEANED', 'VACANT'].includes(saved.qmView)) state.mobile.qmView = saved.qmView;
    const searchInput = $('mobileSearch');
    if (searchInput) searchInput.value = state.mobile.search;
  }

  function saveMobileViewPreference_() { // (탭·필터·검색 변경 즉시 저장)
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    if (!role) return;
    try {
      localStorage.setItem(mobileViewPreferenceKey_(), JSON.stringify({
        filter: String(state.mobile.filter || ''),
        search: String(state.mobile.search || ''),
        qmView: role === 'QM' ? String(state.mobile.qmView || 'TARGETS') : ''
      }));
    } catch (ignore) {}
  }

'''
updated = updated.replace(anchor, helpers + anchor, 1)

# 2) 새로고침 직전 스크롤을 state에도 즉시 반영하고 현재 모바일 화면상태를 저장합니다.
old_save_head = """  function saveUiState() { // (스크롤·메뉴·선택 업무일자 저장)\n    sessionStorage.setItem('novaScrollY', String(window.scrollY || 0));\n"""
new_save_head = """  function saveUiState() { // (스크롤·메뉴·선택 업무일자 저장)\n    state.scrollY = Number(window.scrollY || 0); // MOBILE_VIEW_STATE_PERSIST_V2\n    sessionStorage.setItem('novaScrollY', String(state.scrollY));\n"""
if old_save_head not in updated:
    print('ERROR: saveUiState head not found.', file=sys.stderr)
    sys.exit(21)
updated = updated.replace(old_save_head, new_save_head, 1)

old_save_tail = """    saveMobileLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n    saveQmBrowseLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n  }\n"""
new_save_tail = """    saveMobileLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n    saveQmBrowseLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n    saveMobileViewPreference_(); // MOBILE_VIEW_STATE_PERSIST_V2\n  }\n"""
if old_save_tail not in updated:
    print('ERROR: saveUiState tail not found.', file=sys.stderr)
    sys.exit(22)
updated = updated.replace(old_save_tail, new_save_tail, 1)

# 3) applyMobileSnapshot에서는 동기적으로 사용자 화면값을 먼저 복원한 뒤 렌더링합니다.
old_apply_snapshot = """    state.mobile.site = result.selection?.site ?? state.mobile.site;\n    sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''));\n    renderMobileData();\n    const mobileRole = String(state.bootstrap?.user?.role || '').toUpperCase();\n"""
new_apply_snapshot = """    state.mobile.site = result.selection?.site ?? state.mobile.site;\n    sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''));\n    restoreMobileViewPreference_(); // MOBILE_VIEW_STATE_PERSIST_V2\n    renderMobileData();\n    const mobileRole = String(state.bootstrap?.user?.role || '').toUpperCase();\n"""
if old_apply_snapshot not in updated:
    print('ERROR: applyMobileSnapshot render anchor not found.', file=sys.stderr)
    sys.exit(23)
updated = updated.replace(old_apply_snapshot, new_apply_snapshot, 1)

# 4) async loadMobileSnapshot에서 QM 추가조회 로딩까지 끝난 뒤 최초 스크롤을 복원합니다.
old_load_snapshot = """      applyMobileSnapshot(result);\n      if (options.silent) requestAnimationFrame(() => window.scrollTo({ top: previousY, behavior: 'auto' }));\n      startMobileSync();\n"""
new_load_snapshot = """      applyMobileSnapshot(result);\n      const mobileRole = String(state.bootstrap?.user?.role || '').toUpperCase();\n      if (mobileRole === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n        await loadQmMobileBrowse_({ force: Boolean(options.force) });\n      }\n      if (state.mobile.restoreScrollPending) {\n        state.mobile.restoreScrollPending = false;\n        requestAnimationFrame(() => window.scrollTo({ top: Number(state.scrollY || 0), behavior: 'auto' }));\n      } else if (options.silent) {\n        requestAnimationFrame(() => window.scrollTo({ top: previousY, behavior: 'auto' }));\n      }\n      startMobileSync();\n"""
if old_load_snapshot not in updated:
    print('ERROR: loadMobileSnapshot async anchor not found.', file=sys.stderr)
    sys.exit(24)
updated = updated.replace(old_load_snapshot, new_load_snapshot, 1)

# 5) 페이지 새로고침 후 데이터 렌더링 시 스크롤을 한 번 늦게 복원합니다.
old_mobile_state = """      syncInFlight: false,\n      actionInFlight: 0\n    },\n"""
new_mobile_state = """      syncInFlight: false,\n      actionInFlight: 0,\n      restoreScrollPending: true // MOBILE_VIEW_STATE_PERSIST_V2\n    },\n"""
if old_mobile_state not in updated:
    print('ERROR: mobile state tail not found.', file=sys.stderr)
    sys.exit(25)
updated = updated.replace(old_mobile_state, new_mobile_state, 1)

# 6) 업무일자/사업장 변경 시 현재 탭·필터·검색은 유지하고, 대상 범위의 저장된 동·층을 복원할 수 있게 합니다.
for label, old in [
    ('date clear', "      clearMobileLocationPreferencesForCurrentContext_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n"),
    ('site clear', "      clearMobileLocationPreferencesForCurrentContext_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n"),
]:
    if old not in updated:
        print(f'ERROR: {label} anchor not found.', file=sys.stderr)
        sys.exit(26)
    updated = updated.replace(old, "      // MOBILE_VIEW_STATE_PERSIST_V2 · 새 업무범위의 기존 동·층 저장값은 삭제하지 않습니다.\n", 1)

# 날짜/사업장 변경 핸들러의 강제 TARGETS 복귀 2개만 제거합니다.
reset_line = "      state.mobile.qmView = 'TARGETS';\n"
if updated.count(reset_line) < 3:
    print('ERROR: expected QM TARGETS reset anchors not found.', file=sys.stderr)
    sys.exit(27)
updated = updated.replace(reset_line, "      // MOBILE_VIEW_STATE_PERSIST_V2 · 현재 QM 탭 유지\n", 2)

# 7) 필터·검색·QM 탭 변경 시 즉시 저장합니다.
old_filter = """    $('mobileFilters').querySelectorAll('[data-mobile-filter]').forEach(button => button.addEventListener('click', () => {\n      state.mobile.filter = button.dataset.mobileFilter;\n      renderMobileFilters();\n"""
new_filter = """    $('mobileFilters').querySelectorAll('[data-mobile-filter]').forEach(button => button.addEventListener('click', () => {\n      state.mobile.filter = button.dataset.mobileFilter;\n      saveMobileViewPreference_(); // MOBILE_VIEW_STATE_PERSIST_V2\n      renderMobileFilters();\n"""
if old_filter not in updated:
    print('ERROR: mobile filter listener not found.', file=sys.stderr)
    sys.exit(28)
updated = updated.replace(old_filter, new_filter, 1)

old_search = """    $('mobileSearch').addEventListener('input', event => {\n      state.mobile.search = event.target.value.trim();\n      scheduleUiRender_('mobile-search', renderMobileList, 80);\n"""
new_search = """    $('mobileSearch').addEventListener('input', event => {\n      state.mobile.search = event.target.value.trim();\n      saveMobileViewPreference_(); // MOBILE_VIEW_STATE_PERSIST_V2\n      scheduleUiRender_('mobile-search', renderMobileList, 80);\n"""
if old_search not in updated:
    print('ERROR: mobile search listener not found.', file=sys.stderr)
    sys.exit(29)
updated = updated.replace(old_search, new_search, 1)

old_qm_tab = """      state.mobile.qmView = nextView;\n      state.mobile.qmBrowseLimit = 50;\n"""
new_qm_tab = """      state.mobile.qmView = nextView;\n      saveMobileViewPreference_(); // MOBILE_VIEW_STATE_PERSIST_V2\n      state.mobile.qmBrowseLimit = 50;\n"""
if old_qm_tab not in updated:
    print('ERROR: QM tab listener not found.', file=sys.stderr)
    sys.exit(30)
updated = updated.replace(old_qm_tab, new_qm_tab, 1)

# 8) 추가조회에서 점검을 시작해 TARGETS로 의도적으로 돌아간 경우에도 새 화면을 저장합니다.
old_start_target = """      state.mobile.qmView = 'TARGETS';\n      state.mobile.qmBrowseData = null;\n"""
new_start_target = """      state.mobile.qmView = 'TARGETS';\n      saveMobileViewPreference_(); // MOBILE_VIEW_STATE_PERSIST_V2\n      state.mobile.qmBrowseData = null;\n"""
if old_start_target not in updated:
    print('ERROR: QM start target reset not found.', file=sys.stderr)
    sys.exit(31)
updated = updated.replace(old_start_target, new_start_target, 1)

# 9) loadMobileSnapshot이 QM 추가조회까지 함께 복원하므로 새로고침 버튼의 중복 조회를 제거합니다.
old_sync = """    $('mobileSyncButton').addEventListener('click', async () => {\n      await loadMobileSnapshot({ force: true });\n      if (state.mobile.data?.role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') {\n        await loadQmMobileBrowse_({ force: true });\n      }\n    });\n"""
new_sync = """    $('mobileSyncButton').addEventListener('click', async () => {\n      await loadMobileSnapshot({ force: true });\n    }); // MOBILE_VIEW_STATE_PERSIST_V2\n"""
if old_sync not in updated:
    print('ERROR: mobile sync listener not found.', file=sys.stderr)
    sys.exit(32)
updated = updated.replace(old_sync, new_sync, 1)

path.write_text(updated, encoding='utf-8')
print('Applied MOBILE_VIEW_STATE_PERSIST_V2.')
