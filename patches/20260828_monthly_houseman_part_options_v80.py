from pathlib import Path
import subprocess

CLIENT = Path('Client.html')
MONTHLY = Path('11_Monthly.js')

client = CLIENT.read_text(encoding='utf-8')
monthly = MONTHLY.read_text(encoding='utf-8')

# 1) 월별조회 전용 하우스맨 코드옵션 경량 API 추가.
# 기존 통합인디게이터와 동일한 getCodeIndex_()를 사용하고,
# 드물게 비어 있는 코드캐시가 남아 있으면 해당 캐시만 제거한 뒤 1회 재조회합니다.
server_anchor = """function getMonthlyHistoryExport(token, filters) { // (월별 이력 엑셀용 전체 조회)
"""
server_helper = """function getMonthlyHousemanOrderOptions(token) { // (월별조회 하우스맨 등록창 코드옵션 직접 조회)
  return measureResponse_('getMonthlyHousemanOrderOptions', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    let codeIndex = getCodeIndex_();
    let orderParts = Array.isArray(codeIndex['하우스맨파트']) ? codeIndex['하우스맨파트'] : [];
    let orderItems = Array.isArray(codeIndex['하우스맨품목']) ? codeIndex['하우스맨품목'] : [];

    if (!orderParts.length || !orderItems.length) {
      CacheService.getScriptCache().remove('NOVA_CODE_INDEX_V2');
      codeIndex = getCodeIndex_();
      orderParts = Array.isArray(codeIndex['하우스맨파트']) ? codeIndex['하우스맨파트'] : [];
      orderItems = Array.isArray(codeIndex['하우스맨품목']) ? codeIndex['하우스맨품목'] : [];
    }

    return {
      ok: true,
      orderParts,
      orderItems,
      sites: getMonthlyConfiguredSites_()
    };
  });
}

function getMonthlyHistoryExport(token, filters) { // (월별 이력 엑셀용 전체 조회)
"""
if 'function getMonthlyHousemanOrderOptions(token)' not in monthly:
    if monthly.count(server_anchor) != 1:
        raise SystemExit(f'Monthly server helper anchor count mismatch: {monthly.count(server_anchor)}')
    monthly = monthly.replace(server_anchor, server_helper, 1)

# 2) 등록창 오픈 시 월별조회 응답에 파트/품목이 없으면 전용 API로 즉시 복구합니다.
old_function = """  function openMonthlyHousemanOrderModal_() { // (일별 하우스맨 이력에서 오더 등록)
"""
new_function = """  async function openMonthlyHousemanOrderModal_() { // (일별 하우스맨 이력에서 오더 등록)
"""
if old_function in client:
    if client.count(old_function) != 1:
        raise SystemExit(f'Client monthly modal function target count mismatch: {client.count(old_function)}')
    client = client.replace(old_function, new_function, 1)
elif new_function not in client:
    raise SystemExit('Client monthly modal function was not found')

old_options = """    const options = state.monthly.data?.options || {};
    const sites = Array.isArray(options.sites) ? options.sites : [];
    const parts = Array.isArray(options.orderParts) ? options.orderParts : [];
    const items = Array.isArray(options.orderItems) ? options.orderItems : [];
    const itemDatalist = `<datalist id=\"monthlyHousemanItemSuggestions\">${items.map(item => `<option value=\"${escapeAttr(item.label || item.code || '')}\"></option>`).join('')}</datalist>`;
"""
new_options = """    const options = state.monthly.data?.options || {};
    let sites = Array.isArray(options.sites) ? options.sites.slice() : [];
    let parts = Array.isArray(options.orderParts) ? options.orderParts.slice() : [];
    let items = Array.isArray(options.orderItems) ? options.orderItems.slice() : [];

    if (!parts.length || !items.length) {
      try {
        const fallback = await callServer('getMonthlyHousemanOrderOptions', state.token);
        if (fallback?.ok) {
          if (Array.isArray(fallback.orderParts) && fallback.orderParts.length) parts = fallback.orderParts;
          if (Array.isArray(fallback.orderItems) && fallback.orderItems.length) items = fallback.orderItems;
          if (Array.isArray(fallback.sites)) {
            sites = Array.from(new Set([...sites, ...fallback.sites].map(value => String(value || '').trim()).filter(Boolean)));
          }
          if (state.monthly.data) {
            state.monthly.data.options = Object.assign({}, options, {
              sites,
              orderParts: parts,
              orderItems: items
            });
          }
        }
      } catch (error) {
        console.warn('월별조회 하우스맨 코드옵션 직접조회 실패:', error?.message || error);
      }
    }

    if (!parts.length) {
      showToast('하우스맨 파트 목록을 불러오지 못했습니다. 잠시 후 다시 시도하세요.');
      return;
    }

    const itemDatalist = `<datalist id=\"monthlyHousemanItemSuggestions\">${items.map(item => `<option value=\"${escapeAttr(item.label || item.code || '')}\"></option>`).join('')}</datalist>`;
"""
if 'getMonthlyHousemanOrderOptions' not in client:
    if client.count(old_options) != 1:
        raise SystemExit(f'Client monthly order options target count mismatch: {client.count(old_options)}')
    client = client.replace(old_options, new_options, 1)

# 3) 기존 하우스맨 monthly bundle은 그대로 유지합니다. 정상 시 추가 호출 없이 기존 응답을 사용합니다.
required_client = [
    'async function openMonthlyHousemanOrderModal_()',
    "await callServer('getMonthlyHousemanOrderOptions', state.token)",
    "showToast('하우스맨 파트 목록을 불러오지 못했습니다. 잠시 후 다시 시도하세요.')",
    'let parts = Array.isArray(options.orderParts)',
]
for marker in required_client:
    if marker not in client:
        raise SystemExit(f'Missing Client marker after patch: {marker}')

required_monthly = [
    'function getMonthlyHousemanOrderOptions(token)',
    "requireRole_(token, ['ADMIN', 'ORDER'])",
    "CacheService.getScriptCache().remove('NOVA_CODE_INDEX_V2')",
    "codeIndex['하우스맨파트']",
    "codeIndex['하우스맨품목']",
]
for marker in required_monthly:
    if marker not in monthly:
        raise SystemExit(f'Missing Monthly marker after patch: {marker}')

CLIENT.write_text(client, encoding='utf-8')
MONTHLY.write_text(monthly, encoding='utf-8')

changed = [line.strip() for line in subprocess.check_output(['git', 'diff', '--name-only'], text=True).splitlines() if line.strip()]
allowed = {'Client.html', '11_Monthly.js'}
unexpected = [path for path in changed if path not in allowed]
if unexpected:
    raise SystemExit(f'Unexpected source changes: {unexpected}')

print('MONTHLY_HOUSEMAN_PART_OPTIONS_V80_OK')
print('Changed: Client.html, 11_Monthly.js only')
print('Monthly houseman modal reuses the same code source as the indicator and repairs an empty code cache once')
print('Existing monthly response remains the primary path; fallback runs only when part/item options are missing')
