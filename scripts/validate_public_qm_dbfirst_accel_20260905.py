from pathlib import Path

client = Path('Client.html').read_text(encoding='utf-8')
bridge = Path('RealtimeBridge.js').read_text(encoding='utf-8')

checks = {
    'client marker': 'PUBLIC_QM_DBFIRST_ACCEL_20260905' in client,
    'PUBLIC RPC': 'rest/v1/rpc/nova_create_public_houseman_order' in client,
    'PUBLIC-only switch': "requestRole === 'PUBLIC'" in client,
    'non-PUBLIC Cloud Run preserved': "novaRealtimeFetch_('/v1/houseman-orders'" in client,
    'PUBLIC JWT clock-skew retry': client.count("PGRST303") >= 2,
    'QM draft RPC preserved': 'rest/v1/rpc/nova_save_qm_draft' in client,
    'QM legacy Sheet fallback preserved': "callServer('saveQmInspectionDraft'" in client,
    'QM final submit preserved': 'async function submitQmInspectionFinal_' in client,
    'QM all-role promotion marker': 'QM_DRAFT_PROMOTE_ALL_20260905' in bridge,
    'QM role verification': "String(user.role || '').trim().toUpperCase() === 'QM'" in bridge,
    'QM kill switch preserved': "qmDraftMode === 'CANARY' || qmDraftMode === 'Y'" in bridge,
}

forbidden = {
    'browser service-role env': 'SUPABASE_SERVICE_ROLE_KEY' in client,
    'browser service_role literal': 'service_role' in client,
}

failed = [name for name, ok in checks.items() if not ok]
unsafe = [name for name, found in forbidden.items() if found]
if failed or unsafe:
    raise SystemExit('Validation failed: ' + ', '.join(failed + unsafe))

print('PUBLIC_QM_DBFIRST_ACCEL_VALIDATION=PASS')
print('PUBLIC_DB_FIRST=RPC_WITH_LEGACY_FALLBACK')
print('QM_DRAFT_DB_FIRST=ALL_QM_WITH_KILL_SWITCH_AND_SHEET_MIRROR')
print('BROWSER_SERVICE_ROLE_EXPOSURE=NONE')
