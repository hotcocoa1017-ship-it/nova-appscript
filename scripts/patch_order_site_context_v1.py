from pathlib import Path
import sys

MARKER = 'ORDER_SHARED_SITE_CONTEXT_V1'
path = Path('Client.html')
text = path.read_text(encoding='utf-8')

if MARKER in text:
    print('ORDER shared site context patch already applied.')
    raise SystemExit(0)

helper_anchor = "  function saveUiState() { // (스크롤·메뉴·선택 업무일자 저장)"
if helper_anchor not in text:
    print('ERROR: saveUiState anchor not found.', file=sys.stderr)
    raise SystemExit(70)

helper = r'''  /* ORDER_SHARED_SITE_CONTEXT_V1
   * ORDER 계정은 통합 인디케이터에서 조회 확정한 사업장을 현재 업무사업장으로 공유합니다.
   * ADMIN 및 다른 역할에는 영향을 주지 않습니다.
   */
  function isOrderSharedSiteContext_() {
    return String(state.bootstrap?.user?.role || '').trim().toUpperCase() === 'ORDER';
  }

  function getOrderSharedSite_() {
    if (!isOrderSharedSiteContext_()) return '';
    return String(sessionStorage.getItem('novaOrderWorkSite') || '').trim();
  }

  function setOrderSharedSite_(site) {
    if (!isOrderSharedSiteContext_()) return '';
    const nextSite = String(site || '').trim();
    if (!nextSite) return '';
    const previousSite = String(sessionStorage.getItem('novaOrderWorkSite') || '').trim();
    sessionStorage.setItem('novaOrderWorkSite', nextSite);

    const syncState = (bucket, options = {}) => {
      if (!bucket) return;
      const changed = String(bucket.site || '').trim() !== nextSite;
      bucket.site = nextSite;
      if (changed) {
        bucket.loaded = false;
        if (Object.prototype.hasOwnProperty.call(bucket, 'data')) bucket.data = null;
        if (options.resetZoneDraft) bucket.zoneDraft = { employeeNo: '', buildings: [] };
      }
    };

    syncState(state.departure);
    syncState(state.monthly);
    syncState(state.roommaidStats);
    syncState(state.roommaidClose);
    syncState(state.shifts, { resetZoneDraft: true });

    sessionStorage.setItem('novaMonthlySite', nextSite);
    sessionStorage.setItem('novaShiftSite', nextSite);
    if (previousSite && previousSite !== nextSite) {
      state.roommaidClose.attendanceDraft = [];
      state.roommaidClose.attendanceDirty = false;
    }
    return nextSite;
  }

  function applyOrderSharedSiteToMenu_(menuId) {
    if (!isOrderSharedSiteContext_()) return '';
    const site = getOrderSharedSite_();
    if (!site) return '';
    const targets = {
      departure: state.departure,
      monthly: state.monthly,
      roommaidStats: state.roommaidStats,
      roommaidClose: state.roommaidClose,
      shifts: state.shifts
    };
    const bucket = targets[menuId];
    if (!bucket) return site;
    const changed = String(bucket.site || '').trim() !== site;
    bucket.site = site;
    if (changed) {
      bucket.loaded = false;
      if (Object.prototype.hasOwnProperty.call(bucket, 'data')) bucket.data = null;
      if (menuId === 'shifts') bucket.zoneDraft = { employeeNo: '', buildings: [] };
    }
    if (menuId === 'monthly') sessionStorage.setItem('novaMonthlySite', site);
    if (menuId === 'shifts') sessionStorage.setItem('novaShiftSite', site);
    return site;
  }

  function lockOrderSharedSiteSelect_(menuId) {
    if (!isOrderSharedSiteContext_()) return;
    const site = getOrderSharedSite_();
    if (!site) return;
    const idByMenu = {
      departure: 'departureSite',
      monthly: 'monthlySite',
      roommaidStats: 'roommaidPerformanceSite',
      roommaidClose: 'roommaidCloseSite',
      shifts: 'shiftSite'
    };
    const select = $(idByMenu[menuId] || '');
    if (!select) return;
    if ([...select.options].some(option => option.value === site)) select.value = site;
    select.disabled = true;
    select.title = `통합 인디케이터 현재 사업장(${site})으로 고정됩니다.`;
  }

'''
text = text.replace(helper_anchor, helper + helper_anchor, 1)

query_anchor = "      sessionStorage.setItem('novaIndicatorBusinessDate', businessDate);\n      sessionStorage.setItem('novaIndicatorSite', site);\n      loadIndicatorSnapshot({ force: true, silent: false });"
if query_anchor not in text:
    print('ERROR: indicator explicit query anchor not found.', file=sys.stderr)
    raise SystemExit(71)
text = text.replace(
    query_anchor,
    "      sessionStorage.setItem('novaIndicatorBusinessDate', businessDate);\n      sessionStorage.setItem('novaIndicatorSite', site);\n      setOrderSharedSite_(site);\n      loadIndicatorSnapshot({ force: true, silent: false });",
    1
)

for menu_id, shell_line in [
    ('departure', '      renderDepartureDelayShell_();'),
    ('monthly', '      renderMonthlyShell();'),
    ('roommaidStats', '      renderRoommaidPerformanceShell_();'),
    ('roommaidClose', '      renderRoommaidCloseShell_();'),
    ('shifts', '      renderShiftManagementShell_();'),
]:
    anchor = f"    if (menuId === '{menu_id}') {{\n{shell_line}"
    if anchor not in text:
        print(f'ERROR: menu anchor not found: {menu_id}', file=sys.stderr)
        raise SystemExit(72)
    replacement = (
        f"    if (menuId === '{menu_id}') {{\n"
        f"      applyOrderSharedSiteToMenu_(menuId);\n"
        f"{shell_line}\n"
        f"      lockOrderSharedSiteSelect_(menuId);"
    )
    text = text.replace(anchor, replacement, 1)

# Re-apply the disabled lock after option lists are rebuilt from server results.
render_anchors = [
    ("    siteSelect.value = state.departure.site;\n    $('departureBusinessDate').value = state.departure.businessDate;", "departure"),
    ("      sessionStorage.setItem('novaMonthlyType', String(state.monthly.type || 'HOUSEMAN'));\n      renderMonthlyData_();", "monthly"),
    ("    siteSelect.value = state.roommaidStats.site || '';", "roommaidStats"),
    ("      siteSelect.value = data.site || '';\n    }", "roommaidClose"),
    ("    siteSelect.value = state.shifts.site;\n    $('shiftBusinessDate').value = state.shifts.businessDate;", "shifts"),
]
for anchor, menu_id in render_anchors:
    if anchor not in text:
        print(f'ERROR: render anchor not found: {menu_id}', file=sys.stderr)
        raise SystemExit(73)
    if menu_id == 'monthly':
        replacement = anchor + "\n      lockOrderSharedSiteSelect_('monthly');"
    elif menu_id == 'roommaidClose':
        replacement = "      siteSelect.value = data.site || '';\n      lockOrderSharedSiteSelect_('roommaidClose');\n    }"
    else:
        replacement = anchor + f"\n    lockOrderSharedSiteSelect_('{menu_id}');"
    text = text.replace(anchor, replacement, 1)

path.write_text(text, encoding='utf-8')
print('Applied ORDER shared work-site context across indicator dependent menus.')
