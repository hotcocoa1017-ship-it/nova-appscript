from pathlib import Path

SERVER = Path('16_QmChecklist.js')
CLIENT = Path('Client.html')
MARKER = 'QM_FINALIZE_PREFLIGHT_V2'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'ERROR: {label} anchor count={count}, expected=1')
    return text.replace(old, new, 1)


server = SERVER.read_text(encoding='utf-8')
if MARKER not in server:
    anchor = "function submitQmChecklistInspection(token, payload) { // (최종 점검결과 저장·불량 성과 연계)\n"
    block = r'''// QM_FINALIZE_PREFLIGHT_V2
// DB 최종확정 전에 기존 Apps Script 체크리스트 revision/필수값/사진/하자 규칙을 그대로 검증합니다.
// 이 함수는 운영 상태·이력·초안을 쓰지 않는 순수 preflight 입니다.
function prepareQmInspectionFinalizeDbFirst(token, payload) {
  return measureResponse_('prepareQmInspectionFinalizeDbFirst', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || user.defaultSite || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!site || !roomNo) throw new Error('QM 최종점검 식별정보가 없습니다.');

    const checklist = getQmChecklistForSubmit_();
    if (!checklist.items.length) throw new Error('사용 가능한 QM 체크리스트가 없습니다.');
    const requestedRevision = String(safe.revision || '').trim();
    if (requestedRevision && requestedRevision !== checklist.revision) {
      throw new Error('점검 중 체크리스트가 변경되었습니다. 화면을 새로고침한 뒤 다시 점검하세요.');
    }

    const normalizedDraft = normalizeQmDraftPayload_(safe, checklist, {
      answers: [],
      defects: []
    });
    const answers = validateFinalQmAnswers_(normalizedDraft.answers, checklist.items);
    const defects = validateFinalQmDefects_(normalizedDraft.defects, checklist.places);
    const itemFailCount = answers.filter(answer => String(answer.result || '').trim().toUpperCase() === 'FAIL').length;
    const resultStatus = itemFailCount || defects.length ? 'FAIL' : 'PASS';

    return {
      ok: true,
      preflight: true,
      businessDate,
      site,
      roomNo,
      revision: checklist.revision,
      answers,
      defects,
      resultStatus,
      itemFailCount,
      customDefectCount: defects.length,
      startedAt: String(safe.startedAt || '').trim(),
      qmEmployeeNo: user.employeeNo
    };
  });
}

'''
    server = replace_once(server, anchor, block + anchor, 'QM submit server function')
    SERVER.write_text(server, encoding='utf-8')

client = CLIENT.read_text(encoding='utf-8')
if MARKER not in client:
    old_sig = "  async function novaQmFinalizeDbFirstV2_(active, draft, passed, requestId) {\n"
    new_sig = "  async function novaQmFinalizeDbFirstV2_(active, preflight, requestId) { // QM_FINALIZE_PREFLIGHT_V2\n"
    client = replace_once(client, old_sig, new_sig, 'V2 finalize helper signature')

    old_payload = r'''        checklistRevision: String(active?.checklist?.revision || ''),
        answers: Array.isArray(draft?.answers) ? draft.answers : [],
        defects: Array.isArray(draft?.defects) ? draft.defects : [],
        resultStatus: passed ? 'PASS' : 'FAIL',
        startedAt: String(active?.draft?.startedAt || ''),'''
    new_payload = r'''        checklistRevision: String(preflight?.revision || active?.checklist?.revision || ''),
        answers: Array.isArray(preflight?.answers) ? preflight.answers : [],
        defects: Array.isArray(preflight?.defects) ? preflight.defects : [],
        resultStatus: String(preflight?.resultStatus || '').trim().toUpperCase(),
        startedAt: String(preflight?.startedAt || active?.draft?.startedAt || ''),'''
    client = replace_once(client, old_payload, new_payload, 'V2 normalized preflight payload')

    old_call = "      let realtime = await novaQmFinalizeDbFirstV2_(active, draft, passed, requestId);\n"
    new_call = r'''      const finalizePreflight = await callServer('prepareQmInspectionFinalizeDbFirst', state.token, {
        businessDate: state.mobile.businessDate,
        site: state.mobile.site,
        roomNo: active.roomNo,
        revision: active.checklist.revision,
        answers: draft.answers,
        defects: draft.defects,
        startedAt: String(active?.draft?.startedAt || '')
      });
      if (!finalizePreflight?.ok || finalizePreflight?.preflight !== true) {
        throw new Error(finalizePreflight?.message || 'QM 최종제출 사전검증에 실패했습니다.');
      }
      // DB와 후행 Sheet 이력이 동일한 정규화 자료를 사용하도록 preflight 결과로 맞춥니다.
      draft.answers = Array.isArray(finalizePreflight.answers) ? finalizePreflight.answers : [];
      draft.defects = Array.isArray(finalizePreflight.defects) ? finalizePreflight.defects : [];
      let realtime = await novaQmFinalizeDbFirstV2_(active, finalizePreflight, requestId);
'''
    client = replace_once(client, old_call, new_call, 'QM V2 direct call with preflight')
    CLIENT.write_text(client, encoding='utf-8')

print('PASS: QM final V2 now reuses legacy checklist revision/final validation before any DB mutation')
