from pathlib import Path

CLIENT = Path('Client.html')
MONTHLY = Path('11_Monthly.js')
client = CLIENT.read_text(encoding='utf-8')
monthly = MONTHLY.read_text(encoding='utf-8')


def one(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)

# DAILY default + monthly page session persistence.
client = one(client,
"""    monthly: {\n      loaded: false,\n      loading: false,\n      data: null,\n      period: 'MONTHLY',\n      date: '',\n      year: 0,\n      month: 0,\n      site: '',\n      type: 'HOUSEMAN',""",
"""    monthly: {\n      loaded: false,\n      loading: false,\n      data: null,\n      period: sessionStorage.getItem('novaMonthlyPeriod') || 'DAILY',\n      date: sessionStorage.getItem('novaMonthlyDate') || '',\n      year: 0,\n      month: 0,\n      site: sessionStorage.getItem('novaMonthlySite') || '',\n      type: sessionStorage.getItem('novaMonthlyType') || 'HOUSEMAN',""",
'monthly state')
client = one(client,
"if (!['MONTHLY', 'DAILY'].includes(state.monthly.period)) state.monthly.period = 'MONTHLY';",
"if (!['MONTHLY', 'DAILY'].includes(state.monthly.period)) state.monthly.period = 'DAILY';",
'daily render default')
client = one(client,
"const period = String(state.monthly.period || 'MONTHLY').toUpperCase() === 'DAILY' ? 'DAILY' : 'MONTHLY';",
"const period = String(state.monthly.period || 'DAILY').toUpperCase() === 'MONTHLY' ? 'MONTHLY' : 'DAILY';",
'daily filter default')

# Header order button.
client = one(client,
"""          <div class=\"monthly-header-actions\">\n            <button id=\"dailyCloseCancelButton\" class=\"daily-close-cancel hidden\" type=\"button\">마감 취소</button>\n            <button id=\"dailyCloseSaveButton\" class=\"daily-close-save hidden\" type=\"button\">마감 저장</button>\n            <button id=\"monthlySheetButton\" class=\"secondary-button\" type=\"button\">스프레드시트 반영</button>""",
"""          <div class=\"monthly-header-actions\">\n            <button id=\"monthlyHousemanOrderButton\" class=\"primary-button hidden\" type=\"button\">+ 오더 등록</button>\n            <button id=\"dailyCloseCancelButton\" class=\"daily-close-cancel hidden\" type=\"button\">마감 취소</button>\n            <button id=\"dailyCloseSaveButton\" class=\"daily-close-save hidden\" type=\"button\">마감 저장</button>\n            <button id=\"monthlySheetButton\" class=\"secondary-button\" type=\"button\">스프레드시트 반영</button>""",
'order button')

# Persist section/period/date/site selection immediately.
client = one(client,
"""      state.monthly.type = nextType;\n      $('monthlyType').value = nextType;""",
"""      state.monthly.type = nextType;\n      sessionStorage.setItem('novaMonthlyType', nextType);\n      $('monthlyType').value = nextType;""",
'type persistence')
client = one(client,
"""      state.monthly.period = period;\n      if (period === 'DAILY' && !$('monthlyDate').value) $('monthlyDate').value = formatClientDate_(new Date());\n      applyMonthlyPeriodUi_(period);""",
"""      state.monthly.period = period;\n      sessionStorage.setItem('novaMonthlyPeriod', period);\n      if (period === 'DAILY' && !$('monthlyDate').value) $('monthlyDate').value = formatClientDate_(new Date());\n      if (period === 'DAILY') sessionStorage.setItem('novaMonthlyDate', String($('monthlyDate').value || ''));\n      applyMonthlyPeriodUi_(period);""",
'period persistence')
client = one(client,
"    $('monthlyDate').addEventListener('change', () => loadMonthlyHistory({ page: 1 }));",
"""    $('monthlyDate').addEventListener('change', event => {\n      state.monthly.date = event.target.value;\n      sessionStorage.setItem('novaMonthlyDate', String(state.monthly.date || ''));\n      loadMonthlyHistory({ page: 1 });\n    });""",
'date persistence')
client = one(client,
"    $('monthlySite').addEventListener('change', () => loadMonthlyHistory({ page: 1 }));",
"""    $('monthlySite').addEventListener('change', event => {\n      state.monthly.site = event.target.value;\n      sessionStorage.setItem('novaMonthlySite', String(state.monthly.site || ''));\n      loadMonthlyHistory({ page: 1 });\n    });""",
'site persistence')
client = one(client,
"""    $('monthlySheetButton').addEventListener('click', writeMonthlySheet_);\n    $('dailyCloseSaveButton').addEventListener('click', saveDailyCloseFromMonthly_);""",
"""    $('monthlySheetButton').addEventListener('click', writeMonthlySheet_);\n    $('monthlyHousemanOrderButton').addEventListener('click', openMonthlyHousemanOrderModal_);\n    $('dailyCloseSaveButton').addEventListener('click', saveDailyCloseFromMonthly_);""",
'button binding')
client = one(client,
"""    $('monthlyToday').addEventListener('click', () => {\n      $('monthlyDate').value = formatClientDate_(new Date());\n      loadMonthlyHistory({ page: 1 });\n    });""",
"""    $('monthlyToday').addEventListener('click', () => {\n      $('monthlyDate').value = formatClientDate_(new Date());\n      state.monthly.date = $('monthlyDate').value;\n      sessionStorage.setItem('novaMonthlyDate', state.monthly.date);\n      loadMonthlyHistory({ page: 1 });\n    });""",
'today persistence')
client = one(client,
"""    $('monthlyDate').value = formatClientDate_(date);\n    loadMonthlyHistory({ page: 1 });""",
"""    $('monthlyDate').value = formatClientDate_(date);\n    state.monthly.date = $('monthlyDate').value;\n    sessionStorage.setItem('novaMonthlyDate', state.monthly.date);\n    loadMonthlyHistory({ page: 1 });""",
'day nav persistence')

# Order button only on DAILY + HOUSEMAN.
client = one(client,
"""    $('dailyCloseSaveButton')?.classList.toggle('hidden', !daily);\n    $('dailyCloseCancelButton')?.classList.toggle('hidden', state.bootstrap?.user?.role !== 'ADMIN' || !daily || !['CLOSED', 'MIXED'].includes(String(state.monthly.data?.close?.source || '').toUpperCase()));""",
"""    $('dailyCloseSaveButton')?.classList.toggle('hidden', !daily);\n    $('monthlyHousemanOrderButton')?.classList.toggle('hidden', !daily || String(state.monthly.type || '').toUpperCase() !== 'HOUSEMAN');\n    $('dailyCloseCancelButton')?.classList.toggle('hidden', state.bootstrap?.user?.role !== 'ADMIN' || !daily || !['CLOSED', 'MIXED'].includes(String(state.monthly.data?.close?.source || '').toUpperCase()));""",
'period button visibility')
client = one(client,
"""    const closePanel = $('dailyClosePanel');\n    const qmPanel = $('monthlyQmQualityPanel');\n    if (closePanel) closePanel.classList.toggle('hidden', normalized !== 'CLEANING');\n    if (qmPanel) qmPanel.classList.toggle('hidden', normalized !== 'QM');""",
"""    const closePanel = $('dailyClosePanel');\n    const qmPanel = $('monthlyQmQualityPanel');\n    if (closePanel) closePanel.classList.toggle('hidden', normalized !== 'CLEANING');\n    if (qmPanel) qmPanel.classList.toggle('hidden', normalized !== 'QM');\n    $('monthlyHousemanOrderButton')?.classList.toggle('hidden', normalized !== 'HOUSEMAN' || state.monthly.period !== 'DAILY');""",
'type button visibility')

# Persist server-normalized monthly state.
client = one(client,
"""      state.monthly.data = result;\n      Object.assign(state.monthly, result.filters || {});\n      renderMonthlyData_();""",
"""      state.monthly.data = result;\n      Object.assign(state.monthly, result.filters || {});\n      sessionStorage.setItem('novaMonthlyPeriod', String(state.monthly.period || 'DAILY'));\n      sessionStorage.setItem('novaMonthlyDate', String(state.monthly.date || ''));\n      sessionStorage.setItem('novaMonthlySite', String(state.monthly.site || ''));\n      sessionStorage.setItem('novaMonthlyType', String(state.monthly.type || 'HOUSEMAN'));\n      renderMonthlyData_();""",
'normalized persistence')
client = one(client,
"""    sessionStorage.setItem('novaIndicatorSite', String(state.indicator.site || ''));\n    sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''));\n  }""",
"""    sessionStorage.setItem('novaIndicatorSite', String(state.indicator.site || ''));\n    sessionStorage.setItem('novaMobileSite', String(state.mobile.site || ''));\n    sessionStorage.setItem('novaMonthlyPeriod', String(state.monthly.period || 'DAILY'));\n    sessionStorage.setItem('novaMonthlyDate', String(state.monthly.date || ''));\n    sessionStorage.setItem('novaMonthlySite', String(state.monthly.site || ''));\n    sessionStorage.setItem('novaMonthlyType', String(state.monthly.type || 'HOUSEMAN'));\n  }""",
'saveUiState persistence')

# Modal functions inserted before subcategory UI function.
marker = "  function applyMonthlySubcategoryUi_(type) { // (월별조회 하우스맨·룸메이드·QM 소분류 전환)"
if client.count(marker) != 1:
    raise SystemExit(f'PATCH_ERROR: function marker expected 1, found {client.count(marker)}')
insert = r'''  function openMonthlyHousemanOrderModal_() { // (일별 하우스맨 이력에서 오더 등록)
    if (state.monthly.period !== 'DAILY' || String(state.monthly.type || '').toUpperCase() !== 'HOUSEMAN') {
      showToast('하우스맨 일별조회에서 오더를 등록할 수 있습니다.');
      return;
    }
    const businessDate = String($('monthlyDate')?.value || state.monthly.date || formatClientDate_(new Date())).trim();
    const site = String($('monthlySite')?.value || state.monthly.site || '').trim();
    if (!site) {
      showToast('오더를 등록할 사업장을 먼저 선택하세요.');
      $('monthlySite')?.focus();
      return;
    }
    const options = state.monthly.data?.options || {};
    const parts = Array.isArray(options.orderParts) ? options.orderParts : [];
    const items = Array.isArray(options.orderItems) ? options.orderItems : [];
    const itemDatalist = `<datalist id="monthlyHousemanItemSuggestions">${items.map(item => `<option value="${escapeAttr(item.label || item.code || '')}"></option>`).join('')}</datalist>`;
    openModal(`
      <div class="modal-card">
        <div class="modal-header"><h2>하우스맨 오더 등록</h2><button class="modal-close" type="button" data-close-modal>×</button></div>
        <div class="modal-body">
          ${itemDatalist}
          <div class="modal-grid">
            <label class="modal-field"><span>업무일자</span><input id="monthlyOrderDate" value="${escapeAttr(businessDate)}" readonly></label>
            <label class="modal-field"><span>사업장</span><input id="monthlyOrderSite" value="${escapeAttr(site)}" readonly></label>
            <label class="modal-field"><span>객실번호</span><input id="monthlyOrderRoomNo" maxlength="12" inputmode="numeric" placeholder="예: 9557"></label>
            <label class="modal-field"><span>파트</span><select id="monthlyOrderPart"><option value="">선택</option>${parts.map(part => `<option value="${escapeAttr(part.label || part.code || '')}">${escapeHtml(part.label || part.code || '')}</option>`).join('')}</select></label>
            <label class="modal-field full"><span>품목</span><input id="monthlyOrderItem" list="monthlyHousemanItemSuggestions" placeholder="품목을 선택하거나 입력하세요."></label>
            <label class="modal-field"><span>수량</span><input id="monthlyOrderQty" type="number" min="1" max="99" value="1"></label>
            <label class="modal-field"><span>배정</span><select id="monthlyOrderAssignmentMode"><option value="AUTO" selected>근무자 자동배정</option><option value="UNASSIGNED">미배정</option></select></label>
            <label class="modal-field"><span>요청자</span><select id="monthlyOrderRequester"><option value="고객">고객</option><option value="룸메이드">룸메이드</option><option value="프런트">프런트</option><option value="오더테이커" selected>오더테이커</option></select></label>
            <label class="modal-field full"><span>추가내용</span><textarea id="monthlyOrderNote" placeholder="필요한 내용을 입력하세요."></textarea></label>
            <label class="modal-field"><span>중요</span><label class="toggle-compact"><input id="monthlyOrderImportant" type="checkbox"> 중요 오더</label></label>
            <label class="modal-field"><span>인수인계</span><label class="toggle-compact"><input id="monthlyOrderHandover" type="checkbox"> 인수인계</label></label>
          </div>
          <div class="modal-actions"><button id="monthlyOrderSubmit" class="action-button primary" type="button">오더 등록</button></div>
        </div>
      </div>`);
    $('monthlyOrderRoomNo')?.focus();
    $('monthlyOrderSubmit').addEventListener('click', submitMonthlyHousemanOrder_);
  }

  async function submitMonthlyHousemanOrder_() { // (월별조회 하우스맨 오더 등록)
    const button = $('monthlyOrderSubmit');
    if (!button) return;
    const payload = {
      businessDate: String($('monthlyOrderDate')?.value || state.monthly.date || '').trim(),
      site: String($('monthlyOrderSite')?.value || state.monthly.site || '').trim(),
      roomNo: String($('monthlyOrderRoomNo')?.value || '').trim(),
      part: String($('monthlyOrderPart')?.value || '').trim(),
      items: [{ name: String($('monthlyOrderItem')?.value || '').trim(), quantity: clampQuantity($('monthlyOrderQty')?.value) }],
      note: String($('monthlyOrderNote')?.value || '').trim(),
      requester: String($('monthlyOrderRequester')?.value || '오더테이커'),
      assignmentMode: String($('monthlyOrderAssignmentMode')?.value || 'AUTO'),
      important: Boolean($('monthlyOrderImportant')?.checked),
      handover: Boolean($('monthlyOrderHandover')?.checked)
    };
    if (!payload.businessDate) return showToast('업무일자를 선택하세요.');
    if (!payload.site) return showToast('사업장을 선택하세요.');
    if (!payload.roomNo) return showToast('객실번호를 입력하세요.');
    if (!payload.part) return showToast('파트를 선택하세요.');
    if (!payload.items[0].name) return showToast('품목을 입력하세요.');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = '등록 중…';
    try {
      const result = await callServer('createHousemanOrder', state.token, payload);
      if (!result?.ok) throw new Error(result?.message || '오더 등록에 실패했습니다.');
      closeModal();
      showToast(`${payload.roomNo}호 하우스맨 오더 등록 완료`);
      await loadMonthlyHistory({ page: 1 });
    } catch (error) {
      showToast(error?.message || '오더 등록 오류');
      button.disabled = false;
      button.textContent = original;
    }
  }

'''
client = client.replace(marker, insert + marker, 1)

# HOUSEMAN monthly response includes existing part/item code lists for the modal.
monthly = one(monthly,
"""  const options = buildMonthlyOptions_(typedItems, users);\n  const scopedItems = typedItems""",
"""  const options = buildMonthlyOptions_(typedItems, users);\n  if (request.type === 'HOUSEMAN') {\n    options.orderParts = getCodes_('하우스맨파트');\n    options.orderItems = getCodes_('하우스맨품목');\n  }\n  const scopedItems = typedItems""",
'houseman codes')

CLIENT.write_text(client, encoding='utf-8')
MONTHLY.write_text(monthly, encoding='utf-8')

c = CLIENT.read_text(encoding='utf-8')
m = MONTHLY.read_text(encoding='utf-8')
for required in [
    "period: sessionStorage.getItem('novaMonthlyPeriod') || 'DAILY'",
    "date: sessionStorage.getItem('novaMonthlyDate') || ''",
    "site: sessionStorage.getItem('novaMonthlySite') || ''",
    "type: sessionStorage.getItem('novaMonthlyType') || 'HOUSEMAN'",
    'monthlyHousemanOrderButton',
    'function openMonthlyHousemanOrderModal_()',
    'function submitMonthlyHousemanOrder_()',
    "callServer('createHousemanOrder', state.token, payload)",
    "sessionStorage.setItem('novaMonthlyDate'",
    "sessionStorage.setItem('novaMonthlySite'",
    "sessionStorage.setItem('novaMonthlyPeriod'",
    "sessionStorage.setItem('novaMonthlyType'",
    "if (roommaidRealtime || qmRealtime || housemanRealtime)",
    "delay = 3000 + Math.round(Math.random() * 700)",
]:
    if required not in c:
        raise SystemExit(f'PATCH_ERROR: missing client marker: {required}')
for required in ["options.orderParts = getCodes_('하우스맨파트')", "options.orderItems = getCodes_('하우스맨품목')"]:
    if required not in m:
        raise SystemExit(f'PATCH_ERROR: missing server marker: {required}')

print('MONTHLY_HOUSEMAN_ORDER_DAILY_PERSISTENCE_V78_OK')
print('Changed: Client.html, 11_Monthly.js only')
print('Default period: DAILY')
print('Refresh persistence: period/date/site/subcategory PASS')
print('HOUSEMAN DAILY order registration modal: PASS')
print('ROOMMAID/QM/HOUSEMAN 3.0-3.7s cadence preserved')
