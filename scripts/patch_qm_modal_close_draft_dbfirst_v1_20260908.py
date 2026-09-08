from pathlib import Path
import re

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
marker = 'QM_MODAL_CLOSE_DRAFT_DB_FIRST_V1'

if marker in text:
    print('QM modal-close draft DB-first patch already applied.')
    raise SystemExit(0)

helper = r'''
  async function novaQmSaveDraftOnCloseDbFirst_(draft) { // QM_MODAL_CLOSE_DRAFT_DB_FIRST_V1
    const active = state.qmChecklist?.activeInspection;
    if (novaRealtime_.qmDraftDbFirstEnabled && novaRealtimeIsEnabled_()) {
      try {
        const dbResult = await novaQmDraftDbFirstSave_(draft);
        if (active?.draft?.draftId === draft?.draftId) {
          active.draft = Object.assign({}, active.draft, {
            answers: draft.answers || [],
            defects: draft.defects || [],
            dbVersion: dbResult.dbVersion
          });
        }
        novaQmScheduleLegacyDraftMirror_(Object.assign({}, active?.draft || draft, {
          answers: draft.answers || [],
          defects: draft.defects || []
        }));
        return { ok: true, savedAt: dbResult.savedAt, draft: active?.draft || draft, dbFirst: true };
      } catch (dbError) {
        console.warn('[NOVA QM] 모달 종료 DB-first 초안 저장 실패 · 기존 Sheet 저장으로 fallback', dbError);
      }
    }
    return callServer('saveQmInspectionDraft', state.token, {
      draftId: draft.draftId,
      draftRowNumber: Number(draft.rowNumber || 0),
      answers: draft.answers || [],
      defects: draft.defects || []
    });
  }

'''

anchor = '  function closeModal() { // (모달 닫기·QM 진행중 초안 보존)'
if anchor not in text:
    raise SystemExit('ERROR: closeModal anchor not found')
text = text.replace(anchor, helper + anchor, 1)

start = text.index(anchor)
next_function = text.find('\n  function ', start + len(anchor))
if next_function < 0:
    next_function = min(len(text), start + 5000)
block = text[start:next_function]

pattern = re.compile(
    r"callServer\('saveQmInspectionDraft',\s*state\.token,\s*\{\s*"
    r"draftId:\s*draft\.draftId,\s*"
    r"answers:\s*draft\.answers\s*\|\|\s*\[\],\s*"
    r"defects:\s*draft\.defects\s*\|\|\s*\[\]\s*"
    r"\}\)"
)
new_block, count = pattern.subn('novaQmSaveDraftOnCloseDbFirst_(draft)', block, count=1)
if count != 1:
    raise SystemExit(f'ERROR: expected one direct closeModal draft save, found {count}')
text = text[:start] + new_block + text[next_function:]

path.write_text(text, encoding='utf-8')
print('Applied QM modal-close draft DB-first patch.')
