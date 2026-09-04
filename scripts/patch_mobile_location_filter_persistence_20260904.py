from pathlib import Path
import sys

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
updated = text
marker = 'MOBILE_LOCATION_FILTER_PERSIST_V1'

if marker in updated:
    print('Mobile location filter persistence patch already applied.')
    sys.exit(0)

# 1) 역할별/사용자별/업무일자/사업장 기준 동·층 저장 헬퍼를 추가합니다.
anchor = "  function saveUiState() { // (스크롤·메뉴·선택 업무일자 저장)\n"
if anchor not in updated:
    print('ERROR: saveUiState anchor not found.', file=sys.stderr)
    sys.exit(20)

helpers = r'''  // MOBILE_LOCATION_FILTER_PERSIST_V1
  function mobileLocationPreferenceKey_(scope, view) { // (사용자·역할·업무일자·사업장별 동·층 저장키)
    const employeeNo = String(state.bootstrap?.user?.employeeNo || '').trim() || 'ANON';
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase() || 'UNKNOWN';
    const businessDate = String(state.mobile.businessDate || state.bootstrap?.app?.businessDate || '').trim() || 'NO_DATE';
    const site = String(state.mobile.site || state.bootstrap?.user?.defaultSite || '').trim() || 'ALL';
    const suffix = scope === 'QM_BROWSE' ? `:${String(view || qmMobileBrowseView_() || 'TARGETS').toUpperCase()}` : '';
    return `novaMobileLocation:${employeeNo}:${role}:${businessDate}:${site}:${scope || 'COMMON'}${suffix}`;
  }

  function readMobileLocationPreference_(key) { // (동·층 설정 안전조회)
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || 'null');
      if (!parsed || typeof parsed !== 'object') return null;
      return {
        building: String(parsed.building || '').trim(),
        floor: String(parsed.floor || '').trim()
      };
    } catch (ignore) {
      return null;
    }
  }

  function restoreMobileLocationPreference_() { // (PUBLIC·ROOMMAID·QM 점검대상 동·층 복원)
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    if (!['PUBLIC', 'ROOMMAID', 'QM'].includes(role)) return;
    if (role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') return;
    const saved = readMobileLocationPreference_(mobileLocationPreferenceKey_('COMMON'));
    if (!saved) return;
    state.mobile.building = saved.building;
    state.mobile.floor = saved.floor;
  }

  function saveMobileLocationPreference_() { // (PUBLIC·ROOMMAID·QM 점검대상 동·층 즉시저장)
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    if (!['PUBLIC', 'ROOMMAID', 'QM'].includes(role)) return;
    if (role === 'QM' && qmMobileBrowseView_() !== 'TARGETS') return;
    try {
      localStorage.setItem(mobileLocationPreferenceKey_('COMMON'), JSON.stringify({
        building: String(state.mobile.building || ''),
        floor: String(state.mobile.floor || '')
      }));
    } catch (ignore) {}
  }

  function restoreQmBrowseLocationPreference_() { // (QM 당일청소완료·공실 동·층 복원)
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    const view = qmMobileBrowseView_();
    if (role !== 'QM' || view === 'TARGETS') return;
    const saved = readMobileLocationPreference_(mobileLocationPreferenceKey_('QM_BROWSE', view));
    if (!saved) return;
    state.mobile.qmBrowseBuilding = saved.building;
    state.mobile.qmBrowseFloor = saved.floor;
  }

  function saveQmBrowseLocationPreference_() { // (QM 추가조회 동·층 즉시저장)
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    const view = qmMobileBrowseView_();
    if (role !== 'QM' || view === 'TARGETS') return;
    try {
      localStorage.setItem(mobileLocationPreferenceKey_('QM_BROWSE', view), JSON.stringify({
        building: String(state.mobile.qmBrowseBuilding || ''),
        floor: String(state.mobile.qmBrowseFloor || '')
      }));
    } catch (ignore) {}
  }

  function clearMobileLocationPreferencesForCurrentContext_() { // (업무일자·사업장 직접 변경 시 새 범위 필터 초기화)
    try {
      localStorage.removeItem(mobileLocationPreferenceKey_('COMMON'));
      ['CLEANED', 'VACANT'].forEach(view => localStorage.removeItem(mobileLocationPreferenceKey_('QM_BROWSE', view)));
    } catch (ignore) {}
  }

'''
updated = updated.replace(anchor, helpers + anchor, 1)

# 2) 일반 저장 시 현재 동·층도 보존합니다.
old_save = "    sessionStorage.setItem('novaMonthlyType', String(state.monthly.type || 'HOUSEMAN'));\n  }\n"
new_save = "    sessionStorage.setItem('novaMonthlyType', String(state.monthly.type || 'HOUSEMAN'));\n    saveMobileLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n    saveQmBrowseLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n  }\n"
if old_save not in updated:
    print('ERROR: saveUiState body anchor not found.', file=sys.stderr)
    sys.exit(21)
updated = updated.replace(old_save, new_save, 1)

# 3) 업무일자/사업장 직접 변경 시에는 새 범위의 저장값을 지우고 필터를 초기화합니다.
old_date = """    $('mobileDate').addEventListener('change', event => {\n      state.mobile.businessDate = event.target.value;\n      if (state.mobile.businessDate) sessionStorage.setItem('novaMobileBusinessDate', state.mobile.businessDate);\n      state.mobile.building = '';\n"""
new_date = """    $('mobileDate').addEventListener('change', event => {\n      state.mobile.businessDate = event.target.value;\n      if (state.mobile.businessDate) sessionStorage.setItem('novaMobileBusinessDate', state.mobile.businessDate);\n      clearMobileLocationPreferencesForCurrentContext_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n      state.mobile.building = '';\n"""
if old_date not in updated:
    print('ERROR: mobile date change anchor not found.', file=sys.stderr)
    sys.exit(22)
updated = updated.replace(old_date, new_date, 1)

old_site = """    $('mobileSite').addEventListener('change', event => {\n      state.mobile.site = event.target.value;\n      sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''));\n      state.mobile.building = '';\n"""
new_site = """    $('mobileSite').addEventListener('change', event => {\n      state.mobile.site = event.target.value;\n      sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''));\n      clearMobileLocationPreferencesForCurrentContext_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n      state.mobile.building = '';\n"""
if old_site not in updated:
    print('ERROR: mobile site change anchor not found.', file=sys.stderr)
    sys.exit(23)
updated = updated.replace(old_site, new_site, 1)

# 4) 필터 선택 즉시 저장합니다.
old_building = """    $('mobileBuilding').addEventListener('change', event => {\n      state.mobile.building = event.target.value;\n      state.mobile.floor = '';\n      renderMobileLocationFilters_();\n"""
new_building = """    $('mobileBuilding').addEventListener('change', event => {\n      state.mobile.building = event.target.value;\n      state.mobile.floor = '';\n      saveMobileLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n      renderMobileLocationFilters_();\n"""
if old_building not in updated:
    print('ERROR: mobile building listener anchor not found.', file=sys.stderr)
    sys.exit(24)
updated = updated.replace(old_building, new_building, 1)

old_floor = """    $('mobileFloor').addEventListener('change', event => {\n      state.mobile.floor = event.target.value;\n      renderMobileSummary();\n"""
new_floor = """    $('mobileFloor').addEventListener('change', event => {\n      state.mobile.floor = event.target.value;\n      saveMobileLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n      renderMobileSummary();\n"""
if old_floor not in updated:
    print('ERROR: mobile floor listener anchor not found.', file=sys.stderr)
    sys.exit(25)
updated = updated.replace(old_floor, new_floor, 1)

old_qm_building = """    $('qmBrowseBuilding').addEventListener('change', event => {\n      state.mobile.qmBrowseBuilding = event.target.value;\n      state.mobile.qmBrowseFloor = '';\n      state.mobile.qmBrowseLimit = 50;\n      renderQmBrowseLocationFilters_();\n"""
new_qm_building = """    $('qmBrowseBuilding').addEventListener('change', event => {\n      state.mobile.qmBrowseBuilding = event.target.value;\n      state.mobile.qmBrowseFloor = '';\n      state.mobile.qmBrowseLimit = 50;\n      saveQmBrowseLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n      renderQmBrowseLocationFilters_();\n"""
if old_qm_building not in updated:
    print('ERROR: QM building listener anchor not found.', file=sys.stderr)
    sys.exit(26)
updated = updated.replace(old_qm_building, new_qm_building, 1)

old_qm_floor = """    $('qmBrowseFloor').addEventListener('change', event => {\n      state.mobile.qmBrowseFloor = event.target.value;\n      state.mobile.qmBrowseLimit = 50;\n      renderMobileList();\n"""
new_qm_floor = """    $('qmBrowseFloor').addEventListener('change', event => {\n      state.mobile.qmBrowseFloor = event.target.value;\n      state.mobile.qmBrowseLimit = 50;\n      saveQmBrowseLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n      renderMobileList();\n"""
if old_qm_floor not in updated:
    print('ERROR: QM floor listener anchor not found.', file=sys.stderr)
    sys.exit(27)
updated = updated.replace(old_qm_floor, new_qm_floor, 1)

# 5) 공통 동·층 패널을 PUBLIC뿐 아니라 ROOMMAID와 QM 점검대상에도 표시하고 새로고침 설정을 복원합니다.
old_location = """  function renderMobileLocationFilters_() { // (객실퍼블릭 동·층 조회 필터)\n    const panel = $('mobilePublicLocationFilters');\n    const buildingSelect = $('mobileBuilding');\n    const floorSelect = $('mobileFloor');\n    if (!panel || !buildingSelect || !floorSelect) return;\n    const isPublic = state.mobile.data?.role === 'PUBLIC';\n    panel.hidden = !isPublic;\n    if (!isPublic) return;\n\n    const rooms = state.mobile.data?.rooms || [];\n"""
new_location = """  function renderMobileLocationFilters_() { // (PUBLIC·ROOMMAID·QM 점검대상 동·층 조회 필터) // MOBILE_LOCATION_FILTER_PERSIST_V1\n    const panel = $('mobilePublicLocationFilters');\n    const buildingSelect = $('mobileBuilding');\n    const floorSelect = $('mobileFloor');\n    if (!panel || !buildingSelect || !floorSelect) return;\n    const role = String(state.mobile.data?.role || '').trim().toUpperCase();\n    const visible = role === 'PUBLIC' || role === 'ROOMMAID' || (role === 'QM' && qmMobileBrowseView_() === 'TARGETS');\n    panel.hidden = !visible;\n    if (!visible) return;\n    restoreMobileLocationPreference_();\n\n    const rooms = state.mobile.data?.rooms || [];\n"""
if old_location not in updated:
    print('ERROR: mobile location renderer anchor not found.', file=sys.stderr)
    sys.exit(28)
updated = updated.replace(old_location, new_location, 1)

# 6) QM 추가조회 필터도 탭/업무일자/사업장별 저장값을 복원합니다.
old_qm_render = """    const visible = role === 'QM' && view !== 'TARGETS';\n    panel.hidden = !visible;\n    if (!visible) return;\n\n    const key = qmMobileBrowseKey_(view);\n"""
new_qm_render = """    const visible = role === 'QM' && view !== 'TARGETS';\n    panel.hidden = !visible;\n    if (!visible) return;\n    restoreQmBrowseLocationPreference_(); // MOBILE_LOCATION_FILTER_PERSIST_V1\n\n    const key = qmMobileBrowseKey_(view);\n"""
if old_qm_render not in updated:
    print('ERROR: QM location renderer anchor not found.', file=sys.stderr)
    sys.exit(29)
updated = updated.replace(old_qm_render, new_qm_render, 1)

# 7) ROOMMAID/QM 점검대상 목록에도 동·층 필터를 적용합니다.
old_filter = """  function filterMobileRoom_(room, query, role) { // (모바일 객실 필터)\n    if (role === 'PUBLIC') {\n      if (state.mobile.building && room.building !== state.mobile.building) return false;\n      if (state.mobile.floor && String(room.floor || '') !== state.mobile.floor) return false;\n      if (state.mobile.filter === 'DELAYED' && !room.departureDelayed) return false;\n      if (!['ALL', 'DELAYED'].includes(state.mobile.filter) && room.roomStatus !== state.mobile.filter) return false;\n    } else {\n"""
new_filter = """  function filterMobileRoom_(room, query, role) { // (모바일 객실 필터) // MOBILE_LOCATION_FILTER_PERSIST_V1\n    if (['PUBLIC', 'ROOMMAID', 'QM'].includes(String(role || '').toUpperCase())) {\n      if (state.mobile.building && room.building !== state.mobile.building) return false;\n      if (state.mobile.floor && String(room.floor || '') !== state.mobile.floor) return false;\n    }\n    if (role === 'PUBLIC') {\n      if (state.mobile.filter === 'DELAYED' && !room.departureDelayed) return false;\n      if (!['ALL', 'DELAYED'].includes(state.mobile.filter) && room.roomStatus !== state.mobile.filter) return false;\n    } else {\n"""
if old_filter not in updated:
    print('ERROR: mobile room filter anchor not found.', file=sys.stderr)
    sys.exit(30)
updated = updated.replace(old_filter, new_filter, 1)

path.write_text(updated, encoding='utf-8')
print('Applied MOBILE_LOCATION_FILTER_PERSIST_V1.')
