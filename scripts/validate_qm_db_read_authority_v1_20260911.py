from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
server = (root / 'QmDbReadAuthority.js').read_text(encoding='utf-8')
client = (root / 'QmDbReadAuthorityClient.html').read_text(encoding='utf-8')
index = (root / 'Index.html').read_text(encoding='utf-8')

for marker in [
    'QM_DB_READ_AUTHORITY_V1',
    'function getQmDbReadAuthoritySnapshot',
    "requireRole_(token, ['QM'])",
    "novaQmDbReadAuthorityFetchRooms_",
    "novaQmDbReadAuthorityMergeRooms_",
    "buildQmSummary_(rooms)",
    "rooms.map(qmMobileBrowseRoomDto_)"
]:
    if marker not in server:
        raise SystemExit(f'missing server marker: {marker}')

for forbidden in [
    'setValue(', 'setValues(', 'appendRow(', 'updateRowByHeaders_(',
    'createRowByHeaders_(', 'deleteRow(', 'LockService', 'SpreadsheetApp.flush',
    'reserveDataVersion_', 'publishDataVersion_', '.insert(', '.update(', '.delete('
]:
    if forbidden in server:
        raise SystemExit(f'read authority endpoint contains mutator: {forbidden}')

for marker in [
    'QM_DB_READ_AUTHORITY_V1',
    'const previousCallServer = window.callServer',
    "method === 'getQmMobileBrowseRooms'",
    "method !== 'getMobileSnapshot'",
    "getQmDbReadAuthoritySnapshot",
    'window.callServer = wrappedCallServer'
]:
    if marker not in client:
        raise SystemExit(f'missing client marker: {marker}')

for forbidden in ['preventDefault(', 'stopPropagation(', 'stopImmediatePropagation(']:
    if forbidden in client:
        raise SystemExit(f'QM read overlay intercepts UI events: {forbidden}')

include = "<?!= include_('QmDbReadAuthorityClient'); ?>"
if include not in index:
    raise SystemExit('QM DB read authority include missing from Index.html')
if index.index("include_('Client')") > index.index("include_('QmDbReadAuthorityClient')"):
    raise SystemExit('QM DB read authority must load after Client.html')

print('QM_DB_READ_AUTHORITY_V1 validation passed')
