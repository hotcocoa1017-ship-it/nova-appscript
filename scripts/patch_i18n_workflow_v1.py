from pathlib import Path

path = Path('.github/workflows/deploy-apps-script.yml')
text = path.read_text(encoding='utf-8')
marker = 'Apply login language and bilingual order storage V1'
if marker in text:
    print('NOVA I18N workflow V1 already applied.')
    raise SystemExit(0)

anchor = """      - name: Apply mobile full view state persistence V2\n        run: python3 scripts/patch_mobile_view_state_persistence_20260904.py\n\n"""
insert = anchor + """      - name: Apply login language and bilingual order storage V1\n        run: python3 scripts/patch_i18n_login_order_v1.py\n\n"""
if anchor not in text:
    raise SystemExit('ERROR: i18n workflow apply anchor not found')
text = text.replace(anchor, insert, 1)

validate_anchor = """          grep -q \"새 업무범위의 기존 동·층 저장값은 삭제하지 않습니다\" Client.html\n"""
validate_insert = validate_anchor + """          grep -q \"NOVA_I18N_V1\" Index.html\n          grep -q \"NOVA_I18N_V1\" I18nClient.html\n          grep -q \"function translateNovaHousemanOrderPayload\" I18nServer.js\n          grep -q \"Realtime 오더 번역\" Client.html\n          grep -q \"모바일 오더 저장 전 한국어 변환\" 10_Mobile.js\n          grep -q \"원문/한국어 번역 메타\" 07_Houseman.js\n          grep -q \"사진 오더 원문언어\" HousemanRequestPhotoClient.html\n"""
if validate_anchor not in text:
    raise SystemExit('ERROR: i18n workflow validation anchor not found')
text = text.replace(validate_anchor, validate_insert, 1)

syntax_anchor = """          node --check 03_Auth.js\n          node --check 05_Performance.js\n          node --check 10_Mobile.js\n"""
syntax_insert = """          node --check 03_Auth.js\n          node --check 05_Performance.js\n          node --check 07_Houseman.js\n          node --check 10_Mobile.js\n          node --check I18nServer.js\n"""
if syntax_anchor not in text:
    raise SystemExit('ERROR: i18n workflow server syntax anchor not found')
text = text.replace(syntax_anchor, syntax_insert, 1)

extract_anchor = """              ('Client.html', '/tmp/NovaClient.js'),\n              ('HousemanUiPerformancePatch.html', '/tmp/NovaNotification.js'),\n"""
extract_insert = """              ('Client.html', '/tmp/NovaClient.js'),\n              ('HousemanUiPerformancePatch.html', '/tmp/NovaNotification.js'),\n              ('I18nClient.html', '/tmp/NovaI18n.js'),\n"""
if extract_anchor not in text:
    raise SystemExit('ERROR: i18n workflow client syntax anchor not found')
text = text.replace(extract_anchor, extract_insert, 1)

node_anchor = """          node --check /tmp/NovaClient.js\n          node --check /tmp/NovaNotification.js\n"""
node_insert = """          node --check /tmp/NovaClient.js\n          node --check /tmp/NovaNotification.js\n          node --check /tmp/NovaI18n.js\n"""
if node_anchor not in text:
    raise SystemExit('ERROR: i18n workflow node check anchor not found')
text = text.replace(node_anchor, node_insert, 1)

tracked_old = "tracked=(Index.html 02_Repository.js 03_Auth.js 05_Performance.js 10_Mobile.js 16_QmChecklist.js QmMobileBrowse.js Client.html HousemanUiPerformancePatch.html RealtimeDailySync.js 17_RoommaidPerformance.js 19_RoommaidCloseJournal.js)"
tracked_new = "tracked=(Index.html 02_Repository.js 03_Auth.js 05_Performance.js 07_Houseman.js 10_Mobile.js 16_QmChecklist.js QmMobileBrowse.js Client.html HousemanRequestPhotoClient.html HousemanUiPerformancePatch.html RealtimeDailySync.js 17_RoommaidPerformance.js 19_RoommaidCloseJournal.js)"
if tracked_old not in text:
    raise SystemExit('ERROR: i18n workflow tracked anchor not found')
text = text.replace(tracked_old, tracked_new, 1)

idempotence_anchor = """          python3 scripts/patch_mobile_view_state_persistence_20260904.py\n          python3 scripts/validate_site_scope_indicator_close_v2.py\n"""
idempotence_insert = """          python3 scripts/patch_mobile_view_state_persistence_20260904.py\n          python3 scripts/patch_i18n_login_order_v1.py\n          python3 scripts/validate_site_scope_indicator_close_v2.py\n"""
if idempotence_anchor not in text:
    raise SystemExit('ERROR: i18n workflow idempotence anchor not found')
text = text.replace(idempotence_anchor, idempotence_insert, 1)

generated_old = "generated=(Index.html 02_Repository.js 03_Auth.js 05_Performance.js 10_Mobile.js 16_QmChecklist.js QmMobileBrowse.js Client.html HousemanUiPerformancePatch.html RealtimeDailySync.js 17_RoommaidPerformance.js 19_RoommaidCloseJournal.js)"
generated_new = "generated=(Index.html 02_Repository.js 03_Auth.js 05_Performance.js 07_Houseman.js 10_Mobile.js 16_QmChecklist.js QmMobileBrowse.js Client.html HousemanRequestPhotoClient.html HousemanUiPerformancePatch.html RealtimeDailySync.js 17_RoommaidPerformance.js 19_RoommaidCloseJournal.js)"
if generated_old not in text:
    raise SystemExit('ERROR: i18n workflow generated anchor not found')
text = text.replace(generated_old, generated_new, 1)

path.write_text(text, encoding='utf-8')
print('Applied NOVA I18N workflow V1.')
