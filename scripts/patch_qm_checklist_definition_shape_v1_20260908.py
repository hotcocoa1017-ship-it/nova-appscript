from pathlib import Path
import subprocess
import sys


def replace_once(text, old, new, label):
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        print(f'ERROR: {label}: expected 1 anchor, found {count}', file=sys.stderr)
        raise SystemExit(98)
    return text.replace(old, new, 1)


p = Path('QmChecklistDbFirstBridge.js')
s = p.read_text(encoding='utf-8')
s = replace_once(
    s,
    "  const placeSet = new Set(places.map(place => place.code));\n  const items = rows\n",
    "  const placeMap = {};\n  places.forEach(place => { placeMap[place.code] = place; });\n  const placeSet = new Set(places.map(place => place.code));\n  const items = rows\n",
    'QM DB place map'
)
s = replace_once(
    s,
    "      const meta = novaQmChecklistParseNote_(row.note);\n      return {\n        code: String(row.code || '').trim(),\n        label: String(row.label || '').trim(),\n        placeCode: String(meta.placeCode || '').trim().toUpperCase(),\n        order: Number(row.order || 9999),\n        required: meta.required !== false,\n        photoRequired: meta.photoRequired === true\n      };\n",
    "      const meta = novaQmChecklistParseNote_(row.note);\n      const placeCode = String(meta.placeCode || '').trim().toUpperCase();\n      const place = placeMap[placeCode] || { code: placeCode, label: '객실 전체', order: 9999 };\n      return {\n        code: String(row.code || '').trim(),\n        label: String(row.label || '').trim(),\n        placeCode: place.code,\n        placeLabel: place.label,\n        placeOrder: Number(place.order || 9999),\n        order: Number(row.order || 9999),\n        required: meta.required !== false,\n        photoRequired: meta.photoRequired === true\n      };\n",
    'QM DB item place shape'
)
s = replace_once(
    s,
    "    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'ko'));\n  return {\n    places,\n    items,\n",
    "    .sort((a, b) => a.placeOrder - b.placeOrder || a.order - b.order || a.label.localeCompare(b.label, 'ko'));\n  return {\n    places,\n    items,\n",
    'QM DB item legacy-compatible sort'
)
p.write_text(s, encoding='utf-8')

p = Path('scripts/fix_patch_site_scope_v2.py')
s = p.read_text(encoding='utf-8')
old = "subprocess.run([sys.executable, 'scripts/patch_qm_checklist_codes_dbfirst_v1_20260908.py'], check=True)\nsubprocess.run([sys.executable, 'scripts/validate_qm_checklist_codes_dbfirst_v1_20260908.py'], check=True)\n"
new = "subprocess.run([sys.executable, 'scripts/patch_qm_checklist_codes_dbfirst_v1_20260908.py'], check=True)\nsubprocess.run([sys.executable, 'scripts/patch_qm_checklist_definition_shape_v1_20260908.py'], check=True)\nsubprocess.run([sys.executable, 'scripts/validate_qm_checklist_definition_shape_v1_20260908.py'], check=True)\nsubprocess.run([sys.executable, 'scripts/validate_qm_checklist_codes_dbfirst_v1_20260908.py'], check=True)\n"
if 'patch_qm_checklist_definition_shape_v1_20260908.py' not in s:
    if old not in s:
        print('ERROR: canonical QM checklist block missing', file=sys.stderr)
        raise SystemExit(98)
    s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

# QM 진행 모달을 닫을 때 남아 있던 직접 Sheet 초안 저장도
# 기존 QM draft DB-first helper를 먼저 사용하고 Sheet는 장애 fallback/호환 미러로만 유지합니다.
subprocess.run([sys.executable, 'scripts/patch_qm_modal_close_draft_dbfirst_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_qm_modal_close_draft_dbfirst_v1_20260908.py'], check=True)

print('QM checklist DB definition shape patch applied.')
