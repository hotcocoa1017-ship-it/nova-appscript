from pathlib import Path
import re
import sys

text = Path('Client.html').read_text(encoding='utf-8')
errors = []

checks = {
    'marker': 'LIVE_OPERATION_RETRY_RESILIENCE_V1',
    'fulfilled legacy retry': 'const legacyResult = await callServer(legacyMethod, state.token, legacySafe); // LIVE_OPERATION_RETRY_RESILIENCE_V1',
    'fulfilled transient check': 'if (!isTransientServerError_(legacyResult) || index === delays.length - 1) return legacyResult;',
    'qm busy retry helper': 'async function submitQmInspectionDetailWithBusyRetry_',
    'qm busy only': "if (code !== 'BUSY_RETRY' || index === delays.length - 1) return result;",
    'qm helper wired': 'return submitQmInspectionDetailWithBusyRetry_({ // LIVE_OPERATION_RETRY_RESILIENCE_V1',
}
for label, needle in checks.items():
    if needle not in text:
        errors.append(f'{label}: missing')

# The QM helper must not catch generic network errors. Retrying an ambiguous response could duplicate history.
helper_match = re.search(r'async function submitQmInspectionDetailWithBusyRetry_\(payload\) \{(.*?)\n  \}\n\n  async function submitQmInspectionFinal_', text, re.S)
if not helper_match:
    errors.append('QM helper body not found')
else:
    body = helper_match.group(1)
    if 'catch (' in body or 'catch(' in body:
        errors.append('QM helper must not retry ambiguous rejected/network failures')
    if "code !== 'BUSY_RETRY'" not in body:
        errors.append('QM helper must be BUSY_RETRY-only')

# Existing core routing must remain intact.
for needle in [
    "rawAction === 'START' ? 'CLEANING_START'",
    "rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'",
    "mappedAction === 'QM_COMPLETE'",
    "String(safe.roomStatus || '').trim().toUpperCase() === 'CHECKED_OUT'",
    "await novaRealtime_.supabase.realtime.setAuth(auth.token)",
]:
    if needle not in text:
        errors.append(f'core routing regression: {needle}')

if errors:
    for error in errors:
        print(f'ERROR: {error}', file=sys.stderr)
    raise SystemExit(2)

print('LIVE_OPERATION_RETRY_RESILIENCE_V1 validation passed.')
