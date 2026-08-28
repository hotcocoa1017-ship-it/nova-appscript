from pathlib import Path

source_path = Path('patches/20260828_roommaid_houseman_fast_photo_monthly_v66.py')
source = source_path.read_text(encoding='utf-8')
old = "'photo_client': ['novaCreateRoommaidHousemanRequestFast_', '사진 저장 중', 'mirrorPromise'],"
new = "'photo_client': ['novaCreateRoommaidHousemanRequestFast_', '하우스맨 요청 등록 완료 · 사진', 'mirrorPromise'],"
if source.count(old) != 1:
    raise SystemExit(f'PATCH_ERROR: v66 validation target expected 1 match, found {source.count(old)}')
source = source.replace(old, new, 1)
exec(compile(source, str(source_path), 'exec'), {'__name__': '__main__', '__file__': str(source_path)})
print('ROOMMAID_HOUSEMAN_FAST_PHOTO_MONTHLY_V66_RETRY_OK')
