from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
old = """  .monthly-photo-viewer-meta,\n  .monthly-photo-viewer-nav {\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    gap: 8px;\n  }\n"""
new = """  .monthly-photo-viewer-meta,\n  .monthly-photo-viewer-nav {\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    gap: 8px;\n  }\n  .monthly-photo-viewer-meta {\n    min-width: 0;\n  }\n  .monthly-photo-viewer-meta > span {\n    flex: 1 1 auto;\n    min-width: 0;\n    overflow: hidden;\n    text-overflow: ellipsis;\n    white-space: nowrap;\n  }\n  #monthlyPhotoDownload {\n    flex: 0 0 auto;\n    min-width: 84px;\n    height: 36px;\n    padding: 0 14px;\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    white-space: nowrap;\n    line-height: 1;\n    border-radius: 9px;\n  }\n  @media (max-width: 760px) {\n    #monthlyPhotoDownload {\n      min-width: 88px;\n      height: 38px;\n      padding: 0 14px;\n      font-size: 13px;\n    }\n  }\n"""
count = text.count(old)
if count != 1:
    raise SystemExit(f'PATCH_ERROR: monthly photo viewer meta style: expected 1 match, found {count}')
text = text.replace(old, new, 1)

required = [
    '.monthly-photo-viewer-meta > span',
    '#monthlyPhotoDownload',
    'min-width: 84px;',
    'white-space: nowrap;',
    'text-overflow: ellipsis;'
]
for token in required:
    if token not in text:
        raise SystemExit(f'PATCH_ERROR: required token missing: {token}')

path.write_text(text, encoding='utf-8')
print('MONTHLY_PHOTO_DOWNLOAD_BUTTON_V67_OK')
print('Changed: Client.html only')
print('Filename: single-line ellipsis')
print('Download button: fixed compact width, no wrapping')
