from pathlib import Path
import re

source_path = Path('patches/20260828_houseman_photo_camera_resume_v68.py')
code = source_path.read_text(encoding='utf-8')
pattern = r"^\s*\('explicit camera button'.*?\),\n"
replacement = "    ('explicit camera button', 'id=\"${PHOTO_CAMERA_ID}\" class=\"nova-hm-photo-camera\" type=\"button\"' in photo),\n"
code, count = re.subn(pattern, replacement, code, count=1, flags=re.M)
if count != 1:
    raise SystemExit(f'PATCH_ERROR: retry validation target: expected 1 match, found {count}')
exec(compile(code, str(source_path), 'exec'), {'__name__': '__main__'})
print('HOUSEMAN_PHOTO_CAMERA_RESUME_V68_RETRY_OK')
