from pathlib import Path

FILES = {
    'monthly': Path('11_Monthly.js'),
    'client': Path('Client.html'),
}
texts = {key: path.read_text(encoding='utf-8') for key, path in FILES.items()}


def replace_once(key, old, new, label):
    count = texts[key].count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    texts[key] = texts[key].replace(old, new, 1)


# -----------------------------------------------------------------------------
# 11_Monthly.js
# - getMonthlyHistory reads only the selected domain's record types.
# - Daily close is calculated only for ROOMMAID/CLEANING.
# - QM quality is calculated only for QM.
# - ALL remains supported for legacy spreadsheet/export callers.
# -----------------------------------------------------------------------------
replace_once(
    'monthly',
    """      items: pageItems,\n      close: buildDailyCloseOverviewForRequest_(request),\n      serverTime: nowText_()\n""",
    """      items: pageItems,\n      close: request.type === 'CLEANING' ? buildDailyCloseOverviewForRequest_(request) : {},\n      serverTime: nowText_()\n""",
    'monthly close only for roommaid page'
)

replace_once(
    'monthly',
    """function buildMonthlyHistoryBundle_(request) { // (월별 이력 조회·필터·집계)\n  const rawRows = readMonthlyHistoryRows_(request);\n  const users = getUserIndex_().byEmployeeNo;\n""",
    """function monthlyRecordTypesForType_(type) { // (월별조회 소분류별 실제 조회 기록구분)\n  const normalized = String(type || 'ALL').trim().toUpperCase();\n  if (normalized === 'HOUSEMAN') return [NOVA.RECORD_TYPES.HOUSEMAN_ORDER];\n  if (normalized === 'CLEANING') return [NOVA.RECORD_TYPES.CLEANING];\n  if (normalized === 'QM') return [NOVA.RECORD_TYPES.QM, NOVA.RECORD_TYPES.QM_CHECKLIST];\n  return [\n    NOVA.RECORD_TYPES.CLEANING,\n    NOVA.RECORD_TYPES.QM,\n    NOVA.RECORD_TYPES.QM_CHECKLIST,\n    NOVA.RECORD_TYPES.HOUSEMAN_ORDER\n  ];\n}\n\nfunction buildMonthlyHistoryBundle_(request) { // (월별 이력 조회·필터·집계)\n  const rawRows = readMonthlyHistoryRows_(request, monthlyRecordTypesForType_(request.type));\n  const users = getUserIndex_().byEmployeeNo;\n""",
    'monthly selected record type read'
)

replace_once(
    'monthly',
    """    summary: buildMonthlySummary_(filtered),\n    staffSummary: buildMonthlyStaffSummary_(filtered, users),\n    qmQuality: buildQmQualityAnalyticsFromHistoryRows_(rawRows.map(row => row.data), users, request),\n    options\n""",
    """    summary: buildMonthlySummary_(filtered),\n    staffSummary: buildMonthlyStaffSummary_(filtered, users),\n    qmQuality: request.type === 'QM'\n      ? buildQmQualityAnalyticsFromHistoryRows_(rawRows.map(row => row.data), users, request)\n      : {},\n    options\n""",
    'qm analytics only for qm page'
)


# -----------------------------------------------------------------------------
# Client.html
# - Replace visible 업무구분 dropdown with 3 minimalist subcategory tabs.
# - Keep hidden monthlyType select so existing export/write/filter paths stay intact.
# - Default page: HOUSEMAN.
# - Hide irrelevant close/QM panels by active section.
# -----------------------------------------------------------------------------
replace_once(
    'client',
    """  @media (max-width: 760px) {\n    #monthlyPhotoDownload {\n      min-width: 88px;\n      height: 38px;\n      padding: 0 14px;\n      font-size: 13px;\n    }\n  }\n</style>\n<script>\n""",
    """  @media (max-width: 760px) {\n    #monthlyPhotoDownload {\n      min-width: 88px;\n      height: 38px;\n      padding: 0 14px;\n      font-size: 13px;\n    }\n  }\n\n  .monthly-subcategory-menu {\n    display: grid;\n    grid-template-columns: repeat(3, minmax(0, 1fr));\n    gap: 6px;\n    margin: 0 0 14px;\n    padding: 4px;\n    border: 1px solid #e5e7eb;\n    border-radius: 12px;\n    background: #f8fafc;\n  }\n  .monthly-subcategory-menu button {\n    min-height: 42px;\n    padding: 0 14px;\n    border: 0;\n    border-radius: 9px;\n    background: transparent;\n    color: #6b7280;\n    font-size: 14px;\n    font-weight: 800;\n    white-space: nowrap;\n  }\n  .monthly-subcategory-menu button.active {\n    background: #fff;\n    color: #111827;\n    box-shadow: 0 1px 3px rgba(0,0,0,.08);\n  }\n  .monthly-subcategory-menu button:focus-visible {\n    outline: 2px solid #111827;\n    outline-offset: 1px;\n  }\n  @media (max-width: 760px) {\n    .monthly-subcategory-menu { gap: 4px; margin-bottom: 10px; }\n    .monthly-subcategory-menu button { min-height: 44px; padding: 0 8px; font-size: 13px; }\n  }\n</style>\n<script>\n""",
    'monthly subcategory css'
)

replace_once(
    'client',
    """      type: 'ALL',\n""",
    """      type: 'HOUSEMAN',\n""",
    'monthly default subcategory'
)

replace_once(
    'client',
    """        <div id=\"monthlyControls\" class=\"monthly-controls\">\n""",
    """        <div id=\"monthlySubcategoryMenu\" class=\"monthly-subcategory-menu\" role=\"tablist\" aria-label=\"월별조회 소분류\">\n          <button type=\"button\" data-monthly-section=\"HOUSEMAN\" role=\"tab\">하우스맨</button>\n          <button type=\"button\" data-monthly-section=\"CLEANING\" role=\"tab\">룸메이드</button>\n          <button type=\"button\" data-monthly-section=\"QM\" role=\"tab\">QM</button>\n        </div>\n        <select id=\"monthlyType\" class=\"hidden\" aria-hidden=\"true\" tabindex=\"-1\">\n          <option value=\"HOUSEMAN\">하우스맨</option>\n          <option value=\"CLEANING\">룸메이드</option>\n          <option value=\"QM\">QM</option>\n        </select>\n        <div id=\"monthlyControls\" class=\"monthly-controls\">\n""",
    'monthly subcategory menu insert'
)

replace_once(
    'client',
    """          <label><span>업무구분</span><select id=\"monthlyType\"><option value=\"ALL\">전체</option><option value=\"CLEANING\">룸메이드</option><option value=\"QM\">QM</option><option value=\"HOUSEMAN\">하우스맨</option></select></label>\n""",
    """""",
    'remove visible monthly type filter'
)

replace_once(
    'client',
    """    $('monthlyDate').value = state.monthly.date || formatClientDate_(new Date());\n    $('monthlyType').value = state.monthly.type || 'ALL';\n    $('monthlySearch').value = state.monthly.search || '';\n    applyMonthlyPeriodUi_(state.monthly.period);\n\n    $('monthlyPeriodToggle').addEventListener('click', event => {\n""",
    """    $('monthlyDate').value = state.monthly.date || formatClientDate_(new Date());\n    $('monthlyType').value = ['HOUSEMAN', 'CLEANING', 'QM'].includes(String(state.monthly.type || '').toUpperCase())\n      ? String(state.monthly.type).toUpperCase()\n      : 'HOUSEMAN';\n    state.monthly.type = $('monthlyType').value;\n    $('monthlySearch').value = state.monthly.search || '';\n    applyMonthlyPeriodUi_(state.monthly.period);\n    applyMonthlySubcategoryUi_(state.monthly.type);\n\n    $('monthlySubcategoryMenu').addEventListener('click', event => {\n      const button = event.target.closest('[data-monthly-section]');\n      if (!button) return;\n      const nextType = String(button.dataset.monthlySection || '').toUpperCase();\n      if (!['HOUSEMAN', 'CLEANING', 'QM'].includes(nextType) || nextType === state.monthly.type) return;\n      state.monthly.type = nextType;\n      $('monthlyType').value = nextType;\n      state.monthly.employeeNo = '';\n      state.monthly.status = '';\n      state.monthly.page = 1;\n      applyMonthlySubcategoryUi_(nextType);\n      loadMonthlyHistory({ page: 1, resetDetailFilters: true });\n    });\n\n    $('monthlyPeriodToggle').addEventListener('click', event => {\n""",
    'monthly subcategory handlers'
)

replace_once(
    'client',
    """    $('monthlyNextDay').addEventListener('click', () => moveMonthlyDay_(1));\n    $('monthlyType').addEventListener('change', () => loadMonthlyHistory({ page: 1, resetDetailFilters: true }));\n    $('monthlySite').addEventListener('change', () => loadMonthlyHistory({ page: 1 }));\n""",
    """    $('monthlyNextDay').addEventListener('click', () => moveMonthlyDay_(1));\n    $('monthlySite').addEventListener('change', () => loadMonthlyHistory({ page: 1 }));\n""",
    'remove legacy type dropdown listener'
)

replace_once(
    'client',
    """  function applyMonthlyPeriodUi_(period) { // (월별·일별 입력영역 전환)\n""",
    """  function applyMonthlySubcategoryUi_(type) { // (월별조회 하우스맨·룸메이드·QM 소분류 전환)\n    const normalized = ['HOUSEMAN', 'CLEANING', 'QM'].includes(String(type || '').toUpperCase())\n      ? String(type).toUpperCase()\n      : 'HOUSEMAN';\n    state.monthly.type = normalized;\n    if ($('monthlyType')) $('monthlyType').value = normalized;\n    document.querySelectorAll('#monthlySubcategoryMenu [data-monthly-section]').forEach(button => {\n      const active = button.dataset.monthlySection === normalized;\n      button.classList.toggle('active', active);\n      button.setAttribute('aria-selected', active ? 'true' : 'false');\n    });\n    const closePanel = $('dailyClosePanel');\n    const qmPanel = $('monthlyQmQualityPanel');\n    if (closePanel) closePanel.classList.toggle('hidden', normalized !== 'CLEANING');\n    if (qmPanel) qmPanel.classList.toggle('hidden', normalized !== 'QM');\n  }\n\n  function applyMonthlyPeriodUi_(period) { // (월별·일별 입력영역 전환)\n""",
    'monthly subcategory ui function'
)

replace_once(
    'client',
    """      type: String($('monthlyType')?.value || state.monthly.type || 'ALL'),\n""",
    """      type: String($('monthlyType')?.value || state.monthly.type || 'HOUSEMAN'),\n""",
    'monthly filter selected type fallback'
)

replace_once(
    'client',
    """    renderMonthlySummary_(data.summary || {});\n    renderDailyClosePanel_(data.close || {});\n    renderMonthlyQmQuality_(data.qmQuality || {});\n    renderMonthlyStaffSummary_(data.staffSummary || []);\n""",
    """    renderMonthlySummary_(data.summary || {});\n    applyMonthlySubcategoryUi_(state.monthly.type);\n    if (state.monthly.type === 'CLEANING') renderDailyClosePanel_(data.close || {});\n    else if ($('dailyClosePanel')) $('dailyClosePanel').innerHTML = '';\n    if (state.monthly.type === 'QM') renderMonthlyQmQuality_(data.qmQuality || {});\n    else if ($('monthlyQmQualityPanel')) $('monthlyQmQualityPanel').innerHTML = '';\n    renderMonthlyStaffSummary_(data.staffSummary || []);\n""",
    'monthly section specific panels'
)

replace_once(
    'client',
    """    $('monthlyType').value = state.monthly.type;\n    $('monthlySearch').value = state.monthly.search || '';\n""",
    """    $('monthlyType').value = state.monthly.type;\n    applyMonthlySubcategoryUi_(state.monthly.type);\n    $('monthlySearch').value = state.monthly.search || '';\n""",
    'monthly options sync active tab'
)

for key, path in FILES.items():
    if texts[key] != path.read_text(encoding='utf-8'):
        path.write_text(texts[key], encoding='utf-8')

# Self validation: exact requested scope only.
client = FILES['client'].read_text(encoding='utf-8')
monthly = FILES['monthly'].read_text(encoding='utf-8')
checks = [
    ('subcategory menu', 'data-monthly-section="HOUSEMAN"' in client and 'data-monthly-section="CLEANING"' in client and 'data-monthly-section="QM"' in client),
    ('no visible type filter', '<span>업무구분</span><select id="monthlyType"' not in client),
    ('houseman default', "type: 'HOUSEMAN'" in client),
    ('section ui', 'function applyMonthlySubcategoryUi_(type)' in client),
    ('selected record types', 'function monthlyRecordTypesForType_(type)' in monthly and 'readMonthlyHistoryRows_(request, monthlyRecordTypesForType_(request.type))' in monthly),
    ('roommaid close only', "request.type === 'CLEANING' ? buildDailyCloseOverviewForRequest_(request) : {}" in monthly),
    ('qm analytics only', "qmQuality: request.type === 'QM'" in monthly),
    ('houseman photo viewer preserved', 'openMonthlyHousemanPhotoViewer_' in client and 'monthly-photo-button' in client),
]
failed = [name for name, ok in checks if not ok]
if failed:
    raise SystemExit('PATCH_ERROR: validation failed: ' + ', '.join(failed))

print('MONTHLY_SUBCATEGORY_PAGES_V69_OK')
print('Changed: 11_Monthly.js, Client.html only')
print('Pages: HOUSEMAN / CLEANING / QM')
print('Read path: selected record types only')
print('Roommaid close: CLEANING only')
print('QM analytics: QM only')
print('Legacy ALL: backend preserved for spreadsheet/export compatibility')
