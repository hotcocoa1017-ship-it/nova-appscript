from pathlib import Path

checks = {
    'QmDbReadAuthorityClient.html': [
        'QM_DB_READ_AUTHORITY_V1',
        'QM_DB_BUTTON_STABILITY_V1',
        'CACHE_MS = 30000',
        'applyCachedNow_()',
        'getQmDbReadAuthoritySnapshot',
        "status === 'QM_CHECKING' && qmNo === current",
    ],
    'QmDbFirstControlsHotfix.html': [
        'QM_DBFIRST_SAVE_UNBLOCK_V2',
        "START_PENDING_TEXT = '점검 시작 처리 중'",
        "MIRROR_PENDING_TEXT = '저장 준비 중'",
        "MIRROR_ERROR_TEXT = '저장 준비 오류'",
        'saveOnly.disabled = false',
        'submit.disabled = false',
        "#qmChecklistSubmit, #qmInspectionSaveOnly",
        'operationActive = true',
    ],
    'RoommaidCleaningRetentionHotfix.html': [
        'ROOMMAID_CLEANING_CARD_RETENTION_V1',
        'RETAIN_MAX_MS = 90000',
        "action === 'START'",
        "action === 'COMPLETE'",
        'mobile-card-cleaning',
    ],
    'Index.html': [
        "include_('QmDbReadAuthorityClient')",
        "include_('QmDbFirstControlsHotfix')",
        "include_('RoommaidCleaningRetentionHotfix')",
    ],
}

for path, markers in checks.items():
    text = Path(path).read_text(encoding='utf-8')
    missing = [m for m in markers if m not in text]
    if missing:
        raise SystemExit(f'{path}: missing regression markers: {missing}')

# Safety: today fixes must remain isolated from core Client/server mutation paths.
index = Path('Index.html').read_text(encoding='utf-8')
client = Path('Client.html').read_text(encoding='utf-8')
roommaid = Path('RoommaidCleaningRetentionHotfix.html').read_text(encoding='utf-8')
qm_controls = Path('QmDbFirstControlsHotfix.html').read_text(encoding='utf-8')

if 'nova_rooms_current' in roommaid or 'google.script.run' in roommaid:
    raise SystemExit('Roommaid retention hotfix must stay client-only and must not write/read DB directly.')
if 'preventDefault(' in roommaid or 'stopPropagation(' in roommaid or 'stopImmediatePropagation(' in roommaid:
    raise SystemExit('Roommaid retention hotfix must not intercept existing click handlers.')
if 'preventDefault(' in qm_controls or 'stopImmediatePropagation(' in qm_controls:
    raise SystemExit('QM control hotfix must not block existing Client submit handlers.')
if index.index("include_('RoommaidCleaningRetentionHotfix')") > index.index("include_('QmDbReadAuthorityClient')"):
    raise SystemExit('Roommaid retention hotfix should load immediately after Client and before QM overlays.')

print('2026-09-11 incident regression gate: PASS')
