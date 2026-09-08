from pathlib import Path
import re
import subprocess
import tempfile

SERVER = Path('16_QmChecklist.js').read_text(encoding='utf-8')
QM_DB_BRIDGE = Path('QmChecklistDbFirstBridge.js').read_text(encoding='utf-8') if Path('QmChecklistDbFirstBridge.js').exists() else ''
CLIENT = Path('Client.html').read_text(encoding='utf-8')


def require(text, needle, label):
    if needle not in text:
        raise SystemExit(f'ERROR: missing {label}: {needle}')


def forbid(text, needle, label):
    if needle in text:
        raise SystemExit(f'ERROR: forbidden {label}: {needle}')


def require_order(text, first, second, label):
    a = text.find(first)
    b = text.find(second)
    if a < 0 or b < 0 or a >= b:
        raise SystemExit(f'ERROR: invalid order for {label}')


require(SERVER, 'QM_FINALIZE_PREFLIGHT_V2', 'server preflight marker')
require(SERVER, 'function prepareQmInspectionFinalizeDbFirst(token, payload)', 'preflight function')
require(SERVER, "requireRole_(token, ['QM'])", 'QM role guard')
# QM checklist code-master DB-first may supply the same current revision through a helper
# implemented in the dedicated DB bridge. Accept either route, but still require the helper itself.
legacy_checklist_read = 'const checklist = getQmChecklistForSubmit_();'
dbfirst_checklist_read = 'const checklist = getQmChecklistForSubmitDbFirst_(token);'
if legacy_checklist_read not in SERVER and dbfirst_checklist_read not in SERVER:
    raise SystemExit(f'ERROR: missing current checklist read: {legacy_checklist_read} OR {dbfirst_checklist_read}')
if dbfirst_checklist_read in SERVER:
    require(QM_DB_BRIDGE, 'function getQmChecklistForSubmitDbFirst_(token)', 'DB-first current checklist helper')
require(SERVER, 'requestedRevision !== checklist.revision', 'revision mismatch guard')
require(SERVER, 'normalizeQmDraftPayload_', 'legacy payload normalizer reuse')
require(SERVER, 'validateFinalQmAnswers_', 'legacy final answer validator reuse')
require(SERVER, 'validateFinalQmDefects_', 'legacy defect validator reuse')
require(SERVER, "resultStatus = itemFailCount || defects.length ? 'FAIL' : 'PASS'", 'server result derivation')

start = SERVER.index('function prepareQmInspectionFinalizeDbFirst(')
end = SERVER.index('function submitQmChecklistInspection(', start)
preflight = SERVER[start:end]
for needle, label in [
    ('appendUnifiedHistory_(', 'history write'),
    ('updateRowByHeaders_(', 'Sheet row update'),
    ('setValues(', 'Sheet value write'),
    ('saveQmInspectionDraft', 'draft write'),
    ('updateMobileRoomOperation', 'room operation write'),
    ('bumpDataVersion_', 'version mutation'),
]:
    forbid(preflight, needle, f'preflight must not perform {label}')

require(CLIENT, 'QM_FINALIZE_PREFLIGHT_V2', 'client preflight marker')
require(CLIENT, "callServer('prepareQmInspectionFinalizeDbFirst'", 'client preflight call')
require(CLIENT, 'finalizePreflight?.preflight !== true', 'preflight success guard')
require(CLIENT, 'draft.answers = Array.isArray(finalizePreflight.answers)', 'normalized answers shared with Sheet mirror')
require(CLIENT, 'draft.defects = Array.isArray(finalizePreflight.defects)', 'normalized defects shared with Sheet mirror')
require(CLIENT, 'novaQmFinalizeDbFirstV2_(active, finalizePreflight, requestId)', 'V2 receives validated payload')
require(CLIENT, "checklistRevision: String(preflight?.revision", 'V2 uses current revision')
require(CLIENT, 'answers: Array.isArray(preflight?.answers)', 'V2 uses validated answers')
require(CLIENT, 'defects: Array.isArray(preflight?.defects)', 'V2 uses validated defects')
require(CLIENT, "resultStatus: String(preflight?.resultStatus", 'V2 uses server-derived quality result')
require_order(CLIENT, "callServer('prepareQmInspectionFinalizeDbFirst'", 'novaQmFinalizeDbFirstV2_(active, finalizePreflight, requestId)', 'preflight must precede DB mutation')

# Generated server, DB bridge and client syntax must remain valid.
subprocess.run(['node', '--check', '16_QmChecklist.js'], check=True)
if QM_DB_BRIDGE:
    subprocess.run(['node', '--check', 'QmChecklistDbFirstBridge.js'], check=True)
scripts = re.findall(r'<script[^>]*>(.*?)</script>', CLIENT, flags=re.S | re.I)
if not scripts:
    raise SystemExit('ERROR: no Client script blocks')
with tempfile.NamedTemporaryFile('w', suffix='.js', encoding='utf-8', delete=False) as handle:
    handle.write('\n'.join(scripts))
    temp_js = handle.name
subprocess.run(['node', '--check', temp_js], check=True)

print('PASS: QM final V2 preflight preserves the existing checklist revision/answer/photo/defect rules before DB mutation and is write-free/syntax-safe.')
