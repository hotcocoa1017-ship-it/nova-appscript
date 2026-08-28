from pathlib import Path

CLIENT = Path('Client.html')
MONTHLY = Path('11_Monthly.js')

client = CLIENT.read_text(encoding='utf-8')
monthly = MONTHLY.read_text(encoding='utf-8')

old_guard = """    const site = String($('monthlySite')?.value || state.monthly.site || '').trim();
    if (!site) {
      showToast('오더를 등록할 사업장을 먼저 선택하세요.');
      $('monthlySite')?.focus();
      return;
    }
    const options = state.monthly.data?.options || {};
    const parts = Array.isArray(options.orderParts) ? options.orderParts : [];
"""
new_guard = """    const site = String($('monthlySite')?.value || state.monthly.site || '').trim();
    const options = state.monthly.data?.options || {};
    const sites = Array.isArray(options.sites) ? options.sites : [];
    const parts = Array.isArray(options.orderParts) ? options.orderParts : [];
"""
if client.count(old_guard) != 1:
    raise SystemExit(f'Client site guard target count mismatch: {client.count(old_guard)}')
client = client.replace(old_guard, new_guard, 1)

old_site_field = """            <label class=\"modal-field\"><span>사업장</span><input id=\"monthlyOrderSite\" value=\"${escapeAttr(site)}\" readonly></label>
"""
new_site_field = """            <label class=\"modal-field\"><span>사업장</span><select id=\"monthlyOrderSite\"><option value=\"\">사업장 선택</option>${sites.map(optionSite => `<option value=\"${escapeAttr(optionSite)}\"${optionSite === site ? ' selected' : ''}>${escapeHtml(optionSite)}</option>`).join('')}</select></label>
"""
if client.count(old_site_field) != 1:
    raise SystemExit(f'Client monthly order site field target count mismatch: {client.count(old_site_field)}')
client = client.replace(old_site_field, new_site_field, 1)

old_success = """      closeModal();
      showToast(`${payload.roomNo}호 하우스맨 오더 등록 완료`);
      await loadMonthlyHistory({ page: 1 });
"""
new_success = """      closeModal();
      state.monthly.site = payload.site;
      sessionStorage.setItem('novaMonthlySite', payload.site);
      if ($('monthlySite')) $('monthlySite').value = payload.site;
      showToast(`${payload.roomNo}호 하우스맨 오더 등록 완료`);
      await loadMonthlyHistory({ page: 1 });
"""
if client.count(old_success) != 1:
    raise SystemExit(f'Client monthly order success target count mismatch: {client.count(old_success)}')
client = client.replace(old_success, new_success, 1)

old_options = """  const options = buildMonthlyOptions_(typedItems, users);
  if (request.type === 'HOUSEMAN') {
"""
new_options = """  const options = buildMonthlyOptions_(typedItems, users);
  options.sites = Array.from(new Set([...(options.sites || []), ...getMonthlyConfiguredSites_()]))
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b, 'ko'));
  if (request.type === 'HOUSEMAN') {
"""
if monthly.count(old_options) != 1:
    raise SystemExit(f'Monthly options target count mismatch: {monthly.count(old_options)}')
monthly = monthly.replace(old_options, new_options, 1)

helper_anchor = """function buildMonthlyOptions_(items, users) { // (월별 필터 선택 목록)
"""
helper = """function getMonthlyConfiguredSites_() { // (이력 유무와 무관한 객실 사업장 목록)
  const cache = CacheService.getScriptCache();
  const cacheKey = 'NOVA_MONTHLY_CONFIGURED_SITES_V79';
  const cached = cache.get(cacheKey);
  if (cached) {
    try {
      const parsed = JSON.parse(cached);
      if (Array.isArray(parsed)) return parsed;
    } catch (error) { /* 캐시 손상 시 재구성 */ }
  }

  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const headerMap = getHeaderMap_(sheet);
  const siteColumn = headerMap['사업장'];
  if (!siteColumn) return [];

  const sites = Array.from(new Set(
    sheet.getRange(2, siteColumn, lastRow - 1, 1)
      .getDisplayValues()
      .map(row => String(row[0] || '').trim())
      .filter(Boolean)
  )).sort((a, b) => a.localeCompare(b, 'ko'));

  try { cache.put(cacheKey, JSON.stringify(sites), 300); } catch (error) { /* 캐시 저장 실패 무시 */ }
  return sites;
}

function buildMonthlyOptions_(items, users) { // (월별 필터 선택 목록)
"""
if monthly.count(helper_anchor) != 1:
    raise SystemExit(f'Monthly helper anchor count mismatch: {monthly.count(helper_anchor)}')
monthly = monthly.replace(helper_anchor, helper, 1)

required_client = [
    "const sites = Array.isArray(options.sites) ? options.sites : [];",
    'id="monthlyOrderSite"><option value="">사업장 선택</option>',
    "sessionStorage.setItem('novaMonthlySite', payload.site);",
]
for marker in required_client:
    if marker not in client:
        raise SystemExit(f'Missing Client marker after patch: {marker}')

required_monthly = [
    'getMonthlyConfiguredSites_()',
    "const siteColumn = headerMap['사업장'];",
    'NOVA_MONTHLY_CONFIGURED_SITES_V79',
]
for marker in required_monthly:
    if marker not in monthly:
        raise SystemExit(f'Missing Monthly marker after patch: {marker}')

CLIENT.write_text(client, encoding='utf-8')
MONTHLY.write_text(monthly, encoding='utf-8')

print('MONTHLY_HOUSEMAN_SITE_V79_OK')
print('Changed: Client.html, 11_Monthly.js only')
print('Monthly site filter now includes configured current-room sites even when the selected day has no houseman history')
print('Houseman order modal allows direct site selection when the history filter is All sites')
print('Successful registration adopts the selected site into the monthly history filter and refresh persistence')
