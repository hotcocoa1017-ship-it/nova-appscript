from pathlib import Path
import sys

CLIENT = Path('Client.html').read_text(encoding='utf-8')
INDEX = Path('Index.html').read_text(encoding='utf-8')
BRIDGE = Path('QmDbFirstBridge.js').read_text(encoding='utf-8')
MARKER = 'QM_START_DB_FIRST_DIRECT_V1'


def require(condition, label):
    if not condition:
        print(f'[FAIL] {label}', file=sys.stderr)
        sys.exit(91)
    print(f'[OK] {label}')


require(CLIENT.count(MARKER) == 1, 'direct patch marker exactly once')
require("async function novaQmStartBrowseDbFirst_(room, view)" in CLIENT, 'direct DB-first helper exists inside Client source')
require("/rest/v1/rpc/nova_qm_begin_inspection_v1" in CLIENT, 'QM begin RPC is used directly')
require("QM_DB_RESULT_UNKNOWN" in CLIENT, 'ambiguous network result fails closed without legacy double-write')
require("result?.alreadyChecking === true && !result?.draft?.draftId" in CLIENT, 'legacy in-progress session protection remains')
require("novaRealtime_.qmDraftDbFirstEnabled !== true" in CLIENT, 'DB-first feature flag guard remains')
require("novaQmEnsureDbFirstMirror_(active)" in CLIENT, 'background Sheet mirror helper exists')
require("if (active.dbFirst) await novaQmEnsureDbFirstMirror_(active);" in CLIENT, 'final detail waits for DB-first Sheet mirror')
require("if (active?.startPending)" in CLIENT and "입력 내용 임시 보관" in CLIENT, 'pending input is retained without autosave race')
require("점검 시작 처리 중 · 체크는 바로 가능합니다." in CLIENT, 'nonblocking pending UI message exists')
require("점검 시작 확인 중…" not in CLIENT, 'old blocking confirmation message removed')
require(".qm-checklist-modal .modal-body input, .qm-checklist-modal .modal-body textarea, .qm-checklist-modal .modal-body select, .qm-checklist-modal .modal-body button" not in CLIENT, 'full checklist input lock removed')
require("function ensureQmDbFirstDraftSheetMirror" in BRIDGE, 'server Sheet mirror bridge is present')
require("include_('QmDbFirstClient')" not in INDEX, 'ineffective QmDbFirst runtime wrapper removed')
require("include_('QmStartNonBlockingClient')" not in INDEX, 'ineffective nonblocking runtime wrapper removed')

helper_pos = CLIENT.index("async function novaQmStartBrowseDbFirst_(room, view)")
start_pos = CLIENT.index("async function startQmBrowseInspection_(roomNo, button)")
handle_pos = CLIENT.index("async function handleMobileListClick(event)", start_pos)
start_section = CLIENT[start_pos:handle_pos]
helper_section = CLIENT[helper_pos:start_pos]

require(helper_pos < start_pos, 'direct helper is in the same Client scope before start handler')
require("openQmInspectionModal_();" in start_section, 'checklist modal opens before start confirmation completes')
require("const directResult = await novaQmStartBrowseDbFirst_(room, view);" in start_section, 'start handler invokes direct DB-first helper')
require("directResult?.legacyFallback" in start_section, 'legacy fallback remains explicit')
require("collectQmInspectionForm_() || previewActive.draft" in start_section, 'pending form values are captured before confirmed rerender')
require("novaQmMergePendingDraft_" in start_section, 'pending form values are merged with server draft')
require(start_section.index("openQmInspectionModal_();") < start_section.index("const directResult = await novaQmStartBrowseDbFirst_(room, view);"), 'modal opens before direct/legacy network wait')

require("if (response.status === 404 || ['PGRST202', 'PGRST205'].includes(code))" in helper_section, 'legacy fallback only covers explicit missing RPC path')
require("if (response.status === 401 && attempt < 2)" in helper_section, 'auth refresh retry is bounded')
require("if ((response.status === 429 || response.status >= 500) && attempt < 2)" in helper_section, 'server retry is bounded')
require("return send(attempt + 1);" in helper_section, 'retries reuse the same request body/requestId')
require("p_request_id: requestId" in helper_section, 'same requestId is sent to RPC')

print('QM_START_DB_FIRST_DIRECT_V1 validation PASS')
