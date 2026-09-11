from pathlib import Path

root = Path(__file__).resolve().parents[1]
server = (root / 'HousemanOrderPopupExtras.js').read_text(encoding='utf-8')
client = (root / 'HousemanOrderPopupExtrasClient.html').read_text(encoding='utf-8')
index = (root / 'Index.html').read_text(encoding='utf-8')

required_server = [
    'HOUSEMAN_POPUP_CREATOR_PHOTO_V1',
    'function getHousemanOrderPopupExtras',
    "requireRole_(token, ['ADMIN', 'ORDER'])",
    "data['등록사번']",
    'getHousemanRequestPhotosForDisplay_',
]
for marker in required_server:
    if marker not in server:
        raise SystemExit(f'missing server marker: {marker}')

# This endpoint must remain strictly read-only. Popup display must never join the order mutation path.
for forbidden in [
    'setValue(', 'setValues(', 'appendRow(', 'updateRowByHeaders_(',
    'createRowByHeaders_(', 'deleteRow(', 'LockService', 'SpreadsheetApp.flush',
    'reserveDataVersion_', 'publishDataVersion_('
]:
    if forbidden in server:
        raise SystemExit(f'read-only popup endpoint contains mutator: {forbidden}')

required_client = [
    'HOUSEMAN_POPUP_NONBLOCKING_V1',
    ".order-mini-row[data-order-id]",
    '[data-monthly-order-manage]',
    "callAppsScript_('getHousemanOrderPopupExtras'",
    "img.loading = index === 0 ? 'eager' : 'lazy'",
    'window.setTimeout(() => hydratePopupExtras_',
]
for marker in required_client:
    if marker not in client:
        raise SystemExit(f'missing client marker: {marker}')

photo_routes = [
    "callAppsScript_('getHousemanRequestPhoto'",
    "callAppsScript_('getHousemanOrderPopupThumbnail'",
]
if not any(marker in client for marker in photo_routes):
    raise SystemExit('missing validated popup photo route')

loading_markers = ['사진 불러오는 중…', '썸네일 불러오는 중…']
if not any(marker in client for marker in loading_markers):
    raise SystemExit('missing inline photo loading marker')

# Passive observer only: it must not delay, cancel or replace the existing popup click path.
for forbidden in ['preventDefault(', 'stopPropagation(', 'stopImmediatePropagation(']:
    if forbidden in client:
        raise SystemExit(f'popup enhancement intercepts existing click path: {forbidden}')

if '사진보기' in client:
    raise SystemExit('popup enhancement must show photos inline without a photo-view button')

include = "<?!= include_('HousemanOrderPopupExtrasClient'); ?>"
if include not in index:
    raise SystemExit('popup extras client include is missing from Index.html')

photo_batch = "<?!= include_('HousemanRequestPhotoBatchClient'); ?>"
performance_patch = "<?!= include_('HousemanUiPerformancePatch'); ?>"
if not (index.index(photo_batch) < index.index(performance_patch) < index.index(include)):
    raise SystemExit('popup extras client must load after existing houseman photo/performance modules')

print('HOUSEMAN_POPUP_CREATOR_PHOTO_V1 validation passed')
