from pathlib import Path

server = Path('HousemanOrderPopupThumbnail.js').read_text(encoding='utf-8')
client = Path('HousemanOrderPopupExtrasClient.html').read_text(encoding='utf-8')
edge = Path('supabase/functions/nova-houseman-photo-v1/index.ts').read_text(encoding='utf-8')
full = Path('HousemanRequestPhoto.js').read_text(encoding='utf-8')

assert 'HOUSEMAN_POPUP_SERVER_THUMBNAIL_V3' in server
assert 'function getHousemanOrderPopupThumbnail' in server
assert "action: 'thumbnail'" in server
assert "source: 'SUPABASE_TRANSFORM'" in server
assert "source: 'DRIVE_THUMBNAIL'" in server
assert 'thumbnailLink' in server
assert 'Utilities.base64Encode(bytes)' in server
assert 'getHousemanRequestPhoto(' not in server

assert "callAppsScript_('getHousemanOrderPopupThumbnail'" in client
assert "callAppsScript_('getHousemanRequestPhoto'" not in client
assert 'result.signedUrl' in client
assert 'result.base64' in client
assert 'HOUSEMAN_POPUP_NONBLOCKING_V1' in client

assert 'const THUMB_WIDTH = 256;' in edge
assert 'const THUMB_HEIGHT = 256;' in edge
assert 'const THUMB_QUALITY = 55;' in edge
assert 'action === "thumbnail"' in edge
assert 'createSignedUrl(String(row.object_path), 300, {' in edge
assert 'transform:' in edge
assert 'resize: "contain"' in edge
assert 'quality: THUMB_QUALITY' in edge
assert 'action === "view"' in edge
assert 'action === "prepare"' in edge
assert 'action === "finalize"' in edge

# 원본 조회 기능은 별도 유지: 팝업만 썸네일 경로로 전환합니다.
assert 'function getHousemanRequestPhoto(token, payload)' in full
assert 'getHousemanRequestPhotoFromStorage_' in full

print('Houseman server thumbnail v3 validation: OK')
