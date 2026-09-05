from pathlib import Path
import re

MARKER = 'HOUSEMAN_PHOTO_METADATA_COLUMN_V1'

monthly = Path('11_Monthly.js')
text = monthly.read_text(encoding='utf-8')
if MARKER not in text:
    pattern = re.compile(
        r"  const photos = typeCode === 'HOUSEMAN' && Array\.isArray\(detail\.photos\)\n"
        r"    \? detail\.photos\n"
        r"        \.filter\(photo => photo && photo\.fileId\)\n"
        r"        \.slice\(0, NOVA_HOUSEMAN_REQUEST_PHOTO\.MAX_PHOTOS_PER_ORDER\)\n"
        r"        \.map\(photo => \(\{\n"
        r"          fileId: String\(photo\.fileId \|\| ''\),\n"
        r"          name: String\(photo\.name \|\| ''\),\n"
        r"          mimeType: String\(photo\.mimeType \|\| 'image/jpeg'\),\n"
        r"          size: Number\(photo\.size \|\| 0\),\n"
        r"          uploadedAt: String\(photo\.uploadedAt \|\| ''\)\n"
        r"        \}\)\)\n"
        r"    : \[\];"
    )
    replacement = (
        "  const photos = typeCode === 'HOUSEMAN'\n"
        "    ? getHousemanRequestPhotosForDisplay_(data, detail)\n"
        "    : []; // HOUSEMAN_PHOTO_METADATA_COLUMN_V1"
    )
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise SystemExit(f'11_Monthly photo block expected once, found {count}')
    monthly.write_text(text, encoding='utf-8')

photo = Path('HousemanRequestPhoto.js')
text = photo.read_text(encoding='utf-8')
if MARKER not in text:
    old = "    const photos = Array.isArray(detail.photos) ? detail.photos.filter(photo => photo && photo.fileId) : [];"
    new = "    const photos = getHousemanRequestPhotosForDisplay_(orderInfo.data, detail); // HOUSEMAN_PHOTO_METADATA_COLUMN_V1"
    if text.count(old) != 1:
        raise SystemExit(f'HousemanRequestPhoto photo block expected once, found {text.count(old)}')
    text = text.replace(old, new, 1)
    photo.write_text(text, encoding='utf-8')

print('HOUSEMAN_PHOTO_METADATA_COLUMN_V1 patched')
