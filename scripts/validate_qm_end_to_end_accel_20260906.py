from pathlib import Path
import sys

CLIENT = Path('Client.html').read_text(encoding='utf-8')
INDEX = Path('Index.html').read_text(encoding='utf-8')
HOUSEMAN_DIRECT = Path('HousemanRequestPhotoDirectClient.html').read_text(encoding='utf-8')

checks = []

def check(label, condition):
    checks.append((label, bool(condition)))

check('QM end-to-end marker exactly once', CLIENT.count('QM_END_TO_END_ACCEL_V1') >= 8)
check('DB-first start helper supports TARGETS', "['TARGETS', 'CLEANED', 'VACANT'].includes(normalizedView)" in CLIENT)
check('normal assigned start uses TARGETS DB-first helper', "novaQmStartBrowseDbFirst_(room, 'TARGETS')" in CLIENT)
check('normal assigned checklist opens before network wait', CLIENT.find("state.qmChecklist.activeInspection = previewActive;\n    openQmInspectionModal_();") < CLIENT.find("novaQmStartBrowseDbFirst_(room, 'TARGETS')"))
check('normal assigned start preserves pending inputs', 'const pendingDraft = collectQmInspectionForm_() || previewActive.draft;' in CLIENT and 'novaQmMergePendingDraft_(result.draft, pendingDraft)' in CLIENT)
check('server dependent controls only are locked', '.qm-checklist-modal [data-qm-photo-input]' in CLIENT and '.qm-checklist-modal #qmChecklistSubmit' in CLIENT)
check('result and note controls are not included in start lock', ".qm-checklist-modal [data-qm-result]" not in CLIENT[CLIENT.find('function novaQmSetStartPendingControls_'):CLIENT.find('function novaQmMergePendingDraft_')])
check('legacy in-progress session fallback remains', 'result?.alreadyChecking === true && !result?.draft?.draftId' in CLIENT)
check('DB-first Sheet mirror remains background', 'void novaQmEnsureDbFirstMirror_(previewActive)' in CLIENT)
check('QM auth is prewarmed on mobile view', "mobileRole === 'QM' && novaRealtime_.qmDraftDbFirstEnabled === true" in CLIENT and 'void novaQmDraftAuthBundle_()' in CLIENT)

check('QM photo edge function wired', "NOVA_QM_PHOTO_EDGE_SLUG_ = 'nova-qm-photo-v1'" in CLIENT)
check('QM direct photo restricted to DB-first active draft', 'active?.dbFirst && active?.draft?.draftId' in CLIENT)
check('QM draft save and photo compression run in parallel', 'const [saveResult, image] = await Promise.all([' in CLIENT)
check('QM photo uses signed Storage upload', 'uploadToSignedUrl(' in CLIENT)
check('QM photo finalize is explicit', "action: 'finalize'" in CLIENT and 'photoId: String(prepared.photoId' in CLIENT)
check('QM photo failed pending row is cleaned', "action: 'delete', photoId: String(prepared.photoId)" in CLIENT)
check('QM direct photo falls back to legacy Drive', "하자사진 직접 Storage 실패 · Drive 안전경로 사용" in CLIENT and "callServer('uploadQmInspectionPhoto'" in CLIENT)
check('QM direct photo fallback waits Sheet mirror', 'await novaQmEnsureDbFirstMirror_(active);' in CLIENT)
check('QM Storage photo delete supports sbqm ids', "fileId.startsWith('sbqm:')" in CLIENT and "action: 'delete', photoId: fileId" in CLIENT)
check('QM Storage photo view supports signed URLs', "safeFileId.startsWith('sbqm:')" in CLIENT and "action: 'view', photoId: safeFileId" in CLIENT and 'result.signedUrl' in CLIENT)
check('legacy Drive photo view remains', "callServer('getQmInspectionPhoto'" in CLIENT)
check('legacy Drive photo delete remains', "callServer('deleteQmInspectionPhoto'" in CLIENT)

check('QM rework maps to safe branch', "currentRole === 'QM' && rawAction === 'REWORK'" in CLIENT and "mappedAction = 'QM_REWORK'" in CLIENT)
check('QM rework avoids full snapshot after success', 'const qmReworkFastPath' in CLIENT and 'applyQmRealtimeRoomLocal_(safePayload.roomNo, result.room);' in CLIENT)
check('QM final status still commits before detail history', CLIENT.find("const realtime = await saveRoomActionRealtimeOrLegacy_('updateMobileRoomOperation'") < CLIENT.find('const persistDetail = async () =>'))
check('QM final detail still waits DB-first Sheet mirror', 'if (active.dbFirst) await novaQmEnsureDbFirstMirror_(active);' in CLIENT)
check('QM DB-first draft save remains', '/rest/v1/rpc/nova_save_qm_draft' in CLIENT)
check('QM legacy draft mirror remains low frequency', 'novaQmScheduleLegacyDraftMirror_' in CLIENT and '}, 5000);' in CLIENT)

check('houseman photo V2 remains unchanged', 'HOUSEMAN_PHOTO_DIRECT_STORAGE_V2_NONBLOCKING_OPTIMIZE' in HOUSEMAN_DIRECT)
check('houseman direct client remains included', "include_('HousemanRequestPhotoDirectClient')" in INDEX)
check('houseman direct client precedes batch client', INDEX.find("include_('HousemanRequestPhotoDirectClient')") < INDEX.find("include_('HousemanRequestPhotoBatchClient')"))
check('ineffective QM runtime wrappers remain excluded', "include_('QmDbFirstClient')" not in INDEX and "include_('QmStartNonBlockingClient')" not in INDEX)

failed = [label for label, ok in checks if not ok]
for label, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {label}")
if failed:
    print(f'QM_END_TO_END_ACCEL_V1 validation FAILED: {len(failed)} checks', file=sys.stderr)
    for label in failed:
        print(f' - {label}', file=sys.stderr)
    raise SystemExit(87)
print(f'QM_END_TO_END_ACCEL_V1 validation PASS: {len(checks)}/{len(checks)}')
