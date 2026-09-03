from pathlib import Path
import re

bridge = Path('RealtimeBridge.js').read_text(encoding='utf-8')
client = Path('Client.html').read_text(encoding='utf-8')

checks = {
    'bridge marker': 'QM_DRAFT_DB_FIRST_V1' in bridge,
    'client marker': 'QM_DRAFT_DB_FIRST_V1' in client,
    'master flag': 'NOVA_QM_DRAFT_DB_FIRST_ENABLED' in bridge,
    'canary allowlist': 'NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES' in bridge,
    'qm role guard': "String(user.role || '').trim().toUpperCase() === 'QM'" in bridge,
    'direct rpc': '/rest/v1/rpc/nova_save_qm_draft' in client,
    'supabase jwt': "'Authorization': `Bearer ${auth.token}`" in client,
    'request id': 'p_request_id: requestId' in client,
    'expected version': 'p_expected_version: expectedVersion' in client,
    'legacy fallback': "DB-first 자동저장 실패 · 기존 Sheet 저장으로 즉시 fallback" in client,
    'legacy mirror': 'novaQmScheduleLegacyDraftMirror_' in client,
    'final submit preserved': 'async function submitQmInspectionFinal_' in client,
    'existing legacy save preserved': "callServer('saveQmInspectionDraft'" in client,
}

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('QM Draft DB-first validation failed: ' + ', '.join(failed))

# The master flag must be OFF by setup default.
if "props.setProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED', 'N')" not in bridge:
    raise SystemExit('Default OFF safety missing')

# Canary must never enable everyone with an empty allowlist.
if 'qmDraftMasterEnabled && qmDraftEmployees.length && token' not in bridge:
    raise SystemExit('Canary allowlist safety missing')

print('QM_DRAFT_DB_FIRST_V1 validation PASS')
