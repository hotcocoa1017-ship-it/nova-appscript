from pathlib import Path
import re

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
original = text

helper_anchor = "  async function openMonthlyHousemanOrderModal_() { // (일별 하우스맨 이력에서 오더 등록)\n"
if helper_anchor not in text:
    raise SystemExit('openMonthlyHousemanOrderModal_ anchor not found')

helper = r'''  const novaMonthlyHousemanOptionPreload_ = { promise: null };

  function monthlyHousemanOptionSnapshot_() { // (월별조회 하우스맨 등록창 옵션 메모리 스냅샷)
    const options = state.monthly.data?.options || {};
    return {
      sites: Array.isArray(options.sites) ? options.sites.slice() : [],
      parts: Array.isArray(options.orderParts) ? options.orderParts.slice() : [],
      items: Array.isArray(options.orderItems) ? options.orderItems.slice() : []
    };
  }

  function mergeMonthlyHousemanOrderOptions_(fallback) { // (서버 코드옵션을 현재 월별조회 상태에 병합)
    const current = monthlyHousemanOptionSnapshot_();
    const sites = Array.from(new Set([
      ...current.sites,
      ...(Array.isArray(fallback?.sites) ? fallback.sites : [])
    ].map(value => String(value || '').trim()).filter(Boolean)));
    const parts = Array.isArray(fallback?.orderParts) && fallback.orderParts.length
      ? fallback.orderParts.slice()
      : current.parts;
    const items = Array.isArray(fallback?.orderItems) && fallback.orderItems.length
      ? fallback.orderItems.slice()
      : current.items;
    if (state.monthly.data) {
      state.monthly.data.options = Object.assign({}, state.monthly.data.options || {}, {
        sites,
        orderParts: parts,
        orderItems: items
      });
    }
    return { sites, parts, items };
  }

  function preloadMonthlyHousemanOrderOptions_() { // (하우스맨 화면 진입 즉시 파트·품목 백그라운드 사전조회)
    const current = monthlyHousemanOptionSnapshot_();
    if (current.parts.length && current.items.length && current.sites.length) {
      return Promise.resolve(current);
    }
    if (novaMonthlyHousemanOptionPreload_.promise) return novaMonthlyHousemanOptionPreload_.promise;
    const promise = callServer('getMonthlyHousemanOrderOptions', state.token)
      .then(result => {
        if (!result?.ok) throw new Error(result?.message || '하우스맨 등록 옵션을 불러오지 못했습니다.');
        return mergeMonthlyHousemanOrderOptions_(result);
      })
      .finally(() => {
        if (novaMonthlyHousemanOptionPreload_.promise === promise) {
          novaMonthlyHousemanOptionPreload_.promise = null;
        }
      });
    novaMonthlyHousemanOptionPreload_.promise = promise;
    return promise;
  }

  function applyMonthlyHousemanOptionsToOpenModal_(resolved) { // (이미 열린 등록창에 옵션만 비동기 채움)
    if (!$('monthlyOrderPart') || !$('monthlyOrderItem')) return;
    const parts = Array.isArray(resolved?.parts) ? resolved.parts : [];
    const items = Array.isArray(resolved?.items) ? resolved.items : [];
    const sites = Array.isArray(resolved?.sites) ? resolved.sites : [];

    const partSelect = $('monthlyOrderPart');
    const selectedPart = String(partSelect.value || '');
    partSelect.innerHTML = `<option value="">선택</option>${parts.map(part => {
      const value = String(part?.label || part?.code || '').trim();
      return `<option value="${escapeAttr(value)}">${escapeHtml(value)}</option>`;
    }).join('')}`;
    if (selectedPart && parts.some(part => String(part?.label || part?.code || '').trim() === selectedPart)) {
      partSelect.value = selectedPart;
    }
    partSelect.disabled = false;

    const datalist = document.getElementById('monthlyHousemanItemSuggestions');
    if (datalist) {
      datalist.innerHTML = items.map(item => {
        const value = String(item?.label || item?.code || '').trim();
        return `<option value="${escapeAttr(value)}"></option>`;
      }).join('');
    }

    const siteSelect = $('monthlyOrderSite');
    if (siteSelect) {
      const selectedSite = String(siteSelect.value || state.monthly.site || '');
      siteSelect.innerHTML = `<option value="">사업장 선택</option>${sites.map(site => `<option value="${escapeAttr(site)}">${escapeHtml(site)}</option>`).join('')}`;
      if (selectedSite && sites.includes(selectedSite)) siteSelect.value = selectedSite;
      siteSelect.disabled = false;
    }
  }

'''

if 'function preloadMonthlyHousemanOrderOptions_()' not in text:
    text = text.replace(helper_anchor, helper + helper_anchor, 1)

# Replace the old blocking fallback section with a non-blocking preload promise.
pattern = re.compile(
    r"    const options = state\.monthly\.data\?\.options \|\| \{\};\n"
    r"    let sites = Array\.isArray\(options\.sites\) \? options\.sites\.slice\(\) : \[\];\n"
    r"    let parts = Array\.isArray\(options\.orderParts\) \? options\.orderParts\.slice\(\) : \[\];\n"
    r"    let items = Array\.isArray\(options\.orderItems\) \? options\.orderItems\.slice\(\) : \[\];\n\n"
    r"    if \(!parts\.length \|\| !items\.length\) \{.*?\n    \}\n\n"
    r"    if \(!parts\.length\) \{\n"
    r"      showToast\('하우스맨 파트 목록을 불러오지 못했습니다\. 잠시 후 다시 시도하세요\.'\);\n"
    r"      return;\n"
    r"    \}\n",
    re.S,
)
replacement = """    const options = state.monthly.data?.options || {};
    const sites = Array.isArray(options.sites) ? options.sites.slice() : [];
    const parts = Array.isArray(options.orderParts) ? options.orderParts.slice() : [];
    const items = Array.isArray(options.orderItems) ? options.orderItems.slice() : [];
    const optionsPromise = preloadMonthlyHousemanOrderOptions_();
"""
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f'blocking option fallback replacement count={count}')

# If parts are not ready, render the modal immediately with a loading placeholder.
old_part = "<label class=\"modal-field\"><span>파트</span><select id=\"monthlyOrderPart\"><option value=\"\">선택</option>${parts.map(part => `<option value=\"${escapeAttr(part.label || part.code || '')}\">${escapeHtml(part.label || part.code || '')}</option>`).join('')}</select></label>"
new_part = "<label class=\"modal-field\"><span>파트</span><select id=\"monthlyOrderPart\"${parts.length ? '' : ' disabled'}>${parts.length ? `<option value=\"\">선택</option>${parts.map(part => `<option value=\"${escapeAttr(part.label || part.code || '')}\">${escapeHtml(part.label || part.code || '')}</option>`).join('')}` : '<option value=\"\">불러오는 중…</option>'}</select></label>"
if old_part not in text:
    raise SystemExit('monthlyOrderPart markup anchor not found')
text = text.replace(old_part, new_part, 1)

# If sites are not ready, keep the modal open and populate them asynchronously.
old_site = "<label class=\"modal-field\"><span>사업장</span><select id=\"monthlyOrderSite\"><option value=\"\">사업장 선택</option>${sites.map(optionSite => `<option value=\"${escapeAttr(optionSite)}\"${optionSite === site ? ' selected' : ''}>${escapeHtml(optionSite)}</option>`).join('')}</select></label>"
new_site = "<label class=\"modal-field\"><span>사업장</span><select id=\"monthlyOrderSite\"${sites.length ? '' : ' disabled'}><option value=\"\">${sites.length ? '사업장 선택' : '불러오는 중…'}</option>${sites.map(optionSite => `<option value=\"${escapeAttr(optionSite)}\"${optionSite === site ? ' selected' : ''}>${escapeHtml(optionSite)}</option>`).join('')}</select></label>"
if old_site not in text:
    raise SystemExit('monthlyOrderSite markup anchor not found')
text = text.replace(old_site, new_site, 1)

# Populate the already-open modal as soon as the background fetch finishes.
bind_anchor = "    const monthlyItemInput = $('monthlyOrderItem');\n    bindMonthlyKoreanItemInput_(monthlyItemInput);\n"
if bind_anchor not in text:
    raise SystemExit('monthly item bind anchor not found')
text = text.replace(bind_anchor, bind_anchor + "    void optionsPromise.then(applyMonthlyHousemanOptionsToOpenModal_).catch(error => {\n      console.warn('월별조회 하우스맨 등록 옵션 비동기 조회 실패:', error?.message || error);\n      showToast('파트·품목 목록을 불러오지 못했습니다. 다시 시도하세요.');\n    });\n", 1)

# Start preloading as soon as HOUSEMAN subcategory becomes active.
subcategory_anchor = "    state.monthly.type = normalized;\n"
if subcategory_anchor not in text:
    raise SystemExit('monthly subcategory state anchor not found')
text = text.replace(subcategory_anchor, subcategory_anchor + "    if (normalized === 'HOUSEMAN') {\n      void preloadMonthlyHousemanOrderOptions_().catch(error => {\n        console.warn('월별조회 하우스맨 등록 옵션 사전조회 실패:', error?.message || error);\n      });\n    }\n", 1)

# Safety checks: preserve all existing critical flows.
checks = [
    "const optionsPromise = preloadMonthlyHousemanOrderOptions_();",
    "불러오는 중…",
    "applyMonthlyHousemanOptionsToOpenModal_",
    "normalized === 'HOUSEMAN'",
    "bindMonthlyKoreanItemInput_",
    "novaMonthlyRealtimeCreateHousemanOrder_",
    "novaMonthlyRealtimeCancelHousemanOrder_",
    "preserveTable: true",
]
for needle in checks:
    if needle not in text:
        raise SystemExit(f'missing expected guard: {needle}')

if text == original:
    raise SystemExit('no Client.html change produced')

path.write_text(text, encoding='utf-8')
print('MONTHLY_HOUSEMAN_MODAL_FAST_OPEN_V84_OK')
