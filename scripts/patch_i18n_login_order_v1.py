from pathlib import Path
import sys


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'ERROR: {label} anchor not found')
    return text.replace(old, new, 1)

# 1) 로그인 화면 언어선택 + 독립 I18N 클라이언트 include
path = Path('Index.html')
text = path.read_text(encoding='utf-8')
if '<!-- NOVA_I18N_V1 -->' not in text:
    anchor = '      <p class="muted login-guide">일반 직원은 사업장 · 이름 · 사번 순으로 로그인합니다. 관리자·오더테이커는 사업장 선택을 생략할 수 있습니다.</p>\n'
    insert = anchor + '''      <!-- NOVA_I18N_V1 -->\n      <label class="login-language-field">\n        <span>언어</span>\n        <select id="loginLanguage" name="language" autocomplete="language">\n          <option value="ko">한국어</option>\n          <option value="en">English</option>\n          <option value="th">ไทย</option>\n          <option value="mn">Монгол</option>\n        </select>\n      </label>\n'''
    text = replace_once(text, anchor, insert, 'Index language selector')
    include_anchor = "  <?!= include_('HousemanUiPerformancePatch'); ?>\n"
    text = replace_once(text, include_anchor, include_anchor + "  <?!= include_('I18nClient'); ?> <!-- NOVA_I18N_V1 -->\n", 'Index i18n include')
    path.write_text(text, encoding='utf-8')

# 2) Client: Realtime 저장 직전 번역 + 모든 오더 생성 fallback의 언어 전달 + 모바일 요청 sourceLanguage
path = Path('Client.html')
text = path.read_text(encoding='utf-8')
if '// NOVA_I18N_V1 · Realtime 오더 번역' not in text:
    anchor = "  async function novaRealtimeCreateHousemanOrder_(payload, authRetry = 0) { // (Cloud Run/PostgreSQL 등록 확정)\n    if (!novaRealtimeIsEnabled_()) throw new Error('Realtime이 비활성화되어 있습니다.');\n"
    replacement = """  async function novaRealtimeCreateHousemanOrder_(payload, authRetry = 0) { // (Cloud Run/PostgreSQL 등록 확정)\n    // NOVA_I18N_V1 · Realtime 오더 번역: DB에는 한국어 운영값, Sheet JSON에는 원문 메타를 보존합니다.\n    let preparedPayload = Object.assign({}, payload || {});\n    preparedPayload.sourceLanguage = String(\n      preparedPayload.sourceLanguage || window.NOVA_I18N?.getLanguage?.() || 'ko'\n    ).trim().toLowerCase();\n    if (preparedPayload.sourceLanguage !== 'ko'\n        && !(preparedPayload.translation\n          && String(preparedPayload.translation.translatedTo || '').toLowerCase() === 'ko'\n          && String(preparedPayload.translation.status || '').toUpperCase() === 'SUCCESS')) {\n      const translated = await callServer('translateNovaHousemanOrderPayload', state.token, preparedPayload);\n      if (!translated?.ok || !translated.payload) {\n        throw new Error(translated?.message || '오더 한국어 번역에 실패했습니다.');\n      }\n      preparedPayload = translated.payload;\n    }\n    payload = preparedPayload;\n    if (!novaRealtimeIsEnabled_()) throw new Error('Realtime이 비활성화되어 있습니다.');\n"""
    text = replace_once(text, anchor, replacement, 'Client realtime translation')

    mobile_payload = """      const payload = {\n        businessDate: state.mobile.businessDate, site: state.mobile.site, roomNo, part,\n        items: [{ name: item, quantity: clampQuantity($('mobileRequestQty').value) }],\n        note: $('mobileRequestNote').value.trim(), requester: state.bootstrap.user.name\n      };\n"""
    mobile_replacement = """      const payload = {\n        businessDate: state.mobile.businessDate, site: state.mobile.site, roomNo, part,\n        items: [{ name: item, quantity: clampQuantity($('mobileRequestQty').value) }],\n        note: $('mobileRequestNote').value.trim(), requester: state.bootstrap.user.name,\n        sourceLanguage: String(window.NOVA_I18N?.getLanguage?.() || 'ko').toLowerCase() // NOVA_I18N_V1\n      };\n"""
    text = replace_once(text, mobile_payload, mobile_replacement, 'Client mobile order language')

    legacy_call = "      const result = await callServer('createHousemanOrder', state.token, payload);"
    legacy_replacement = """      payload.sourceLanguage = String(payload.sourceLanguage || window.NOVA_I18N?.getLanguage?.() || 'ko').toLowerCase(); // NOVA_I18N_V1\n      const result = await callServer('createHousemanOrder', state.token, payload);"""
    if legacy_call not in text:
        raise SystemExit('ERROR: Client createHousemanOrder fallback call not found')
    text = text.replace(legacy_call, legacy_replacement)
    path.write_text(text, encoding='utf-8')

# 3) 사진 포함 모바일 오더에도 로그인 언어 전달
path = Path('HousemanRequestPhotoClient.html')
text = path.read_text(encoding='utf-8')
if '// NOVA_I18N_V1 · 사진 오더 원문언어' not in text:
    anchor = """    const createPayload = {\n      businessDate,\n      site,\n      roomNo: activeRoomNo,\n      part,\n      items: [{ name: item, quantity: clampHousemanPhotoQuantity_(qtyEl && qtyEl.value) }],\n      note: String(noteEl && noteEl.value || '').trim()\n    };\n"""
    replacement = """    const createPayload = {\n      businessDate,\n      site,\n      roomNo: activeRoomNo,\n      part,\n      items: [{ name: item, quantity: clampHousemanPhotoQuantity_(qtyEl && qtyEl.value) }],\n      note: String(noteEl && noteEl.value || '').trim(),\n      sourceLanguage: String(window.NOVA_I18N?.getLanguage?.() || 'ko').toLowerCase() // NOVA_I18N_V1 · 사진 오더 원문언어\n    };\n"""
    text = replace_once(text, anchor, replacement, 'Photo request language')
    path.write_text(text, encoding='utf-8')

# 4) 서버 공통 오더 정규화: 외국어면 저장 전에 한국어 변환, 번역 메타 보존
path = Path('07_Houseman.js')
text = path.read_text(encoding='utf-8')
if '// NOVA_I18N_V1 · 일반 오더 저장 전 한국어 변환' not in text:
    text = replace_once(
        text,
        "    const safe = normalizeHousemanPayload_(payload);\n",
        "    const safe = normalizeHousemanPayload_(prepareNovaHousemanOrderPayloadForStorage_(payload)); // NOVA_I18N_V1 · 일반 오더 저장 전 한국어 변환\n",
        'Houseman create translation'
    )
    detail_anchor = """      const detail = {\n        items: safe.items,\n        requester: safe.requester,\n"""
    detail_replacement = """      const detail = {\n        items: safe.items,\n        sourceLanguage: safe.sourceLanguage || 'ko', // NOVA_I18N_V1 · 원문/한국어 번역 메타\n        translation: safe.translation || null,\n        requester: safe.requester,\n"""
    text = replace_once(text, detail_anchor, detail_replacement, 'Houseman detail translation metadata')

    normalize_anchor = """    requestSource:\n      String(\n        safe.requestSource\n        || 'ORDER'\n      ).trim(),\n\n    assignedEmployeeNo:\n"""
    normalize_replacement = """    requestSource:\n      String(\n        safe.requestSource\n        || 'ORDER'\n      ).trim(),\n\n    sourceLanguage:\n      typeof normalizeNovaUiLanguage_ === 'function'\n        ? normalizeNovaUiLanguage_(safe.sourceLanguage)\n        : String(safe.sourceLanguage || 'ko').trim().toLowerCase(),\n\n    translation:\n      safe.translation && typeof safe.translation === 'object'\n        ? safe.translation\n        : null,\n\n    assignedEmployeeNo:\n"""
    text = replace_once(text, normalize_anchor, normalize_replacement, 'Houseman normalize translation metadata')
    path.write_text(text, encoding='utf-8')

# 5) 모바일 fallback/Sheet 미러에서도 같은 한국어 운영값과 원문 메타 사용
path = Path('10_Mobile.js')
text = path.read_text(encoding='utf-8')
if '// NOVA_I18N_V1 · 모바일 오더 저장 전 한국어 변환' not in text:
    text = replace_once(
        text,
        "    const rawPayload = payload || {};\n    const safe = normalizeHousemanPayload_(rawPayload);\n",
        "    const rawPayload = prepareNovaHousemanOrderPayloadForStorage_(payload || {}); // NOVA_I18N_V1 · 모바일 오더 저장 전 한국어 변환\n    const safe = normalizeHousemanPayload_(rawPayload);\n",
        'Mobile create translation'
    )
    detail_anchor = """    const detail = {\n      items: safe.items,\n      requester: user.name,\n"""
    detail_replacement = """    const detail = {\n      items: safe.items,\n      sourceLanguage: safe.sourceLanguage || 'ko', // NOVA_I18N_V1 · 원문/한국어 번역 메타\n      translation: safe.translation || null,\n      requester: user.name,\n"""
    text = replace_once(text, detail_anchor, detail_replacement, 'Mobile detail translation metadata')
    path.write_text(text, encoding='utf-8')

print('Applied NOVA_I18N_V1.')
