from pathlib import Path

bridge = Path('RealtimeBridge.js').read_text(encoding='utf-8')
client = Path('Client.html').read_text(encoding='utf-8')

checks = {
    'bridge marker': 'QM_DRAFT_DB_FIRST_V1' in bridge,
    'client marker': 'QM_DRAFT_DB_FIRST_V1' in client,
    'canary marker': 'QM_DRAFT_CANARY_Q001_V1' in bridge,
    'master flag': 'NOVA_QM_DRAFT_DB_FIRST_ENABLED' in bridge,
    'canary allowlist property': 'NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES' in bridge,
    'built-in q001 canary': "Object.freeze(['q001'])" in bridge,
    'kill switch N supported': "qmDraftMode === 'CANARY' || qmDraftMode === 'Y'" in bridge,
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

# Fresh/missing property must canary q001 only; explicit N remains the immediate kill switch.
if "props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED') || 'CANARY'" not in bridge:
    raise SystemExit('Default CANARY safety missing')
if "props.setProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED', 'CANARY')" not in bridge:
    raise SystemExit('Setup CANARY default missing')
if "props.setProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES', 'q001')" not in bridge:
    raise SystemExit('Setup q001 allowlist missing')
if "qmDraftMode === 'CANARY' ? Array.from(qmDraftCanaryEmployees) : qmDraftConfiguredEmployees" not in bridge:
    raise SystemExit('Canary must not use configured broad allowlist')

print('QM_DRAFT_DB_FIRST_V1 q001 canary validation PASS')
