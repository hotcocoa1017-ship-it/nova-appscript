from pathlib import Path
import sys

MARKER = 'NOVA_OPERATION_SETTINGS_DB_FIRST_V1'


def replace_once(text, old, new, label):
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 anchor, found {count}')
    return text.replace(old, new, 1)


# DB RPC allowlist
bridge_path = Path('DbFirstBridge.js')
bridge = bridge_path.read_text(encoding='utf-8')
if "'nova_operation_settings_read_v1'" not in bridge:
    anchor = "    'nova_roommaid_close_cancel_v1', // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1\n"
    insertion = anchor + "    'nova_operation_settings_read_v1', // NOVA_OPERATION_SETTINGS_DB_FIRST_V1\n    'nova_operation_settings_save_v1', // NOVA_OPERATION_SETTINGS_DB_FIRST_V1\n"
    bridge = replace_once(bridge, anchor, insertion, 'DbFirstBridge RPC allowlist')
bridge_path.write_text(bridge, encoding='utf-8')

# Client routes only. UI/layout/permissions are unchanged.
client_path = Path('Client.html')
client = client_path.read_text(encoding='utf-8')
client = replace_once(
    client,
    "callServer('getAdminSettingsData', state.token)",
    "callServer('getAdminSettingsDataDbFirst', state.token) // NOVA_OPERATION_SETTINGS_DB_FIRST_V1",
    'Client admin settings read route'
)
client = replace_once(
    client,
    "callServer('saveAdminOperationSettings', state.token, { values })",
    "callServer('saveAdminOperationSettingsDbFirst', state.token, { values, requestId: novaRealtimeRequestId_('OPERATION_SETTINGS_V1', 'ADMIN') }) // NOVA_OPERATION_SETTINGS_DB_FIRST_V1",
    'Client admin settings save route'
)
client_path.write_text(client, encoding='utf-8')

# Canonical deploy meta-patcher: preserve the cutover on every later NOVA deployment.
canonical_path = Path('scripts/fix_patch_site_scope_v2.py')
canonical = canonical_path.read_text(encoding='utf-8')
block = """
# 관리자 운영설정은 PostgreSQL을 쓰기 권위로 사용하고 코드설정 Sheet는 호환 미러로 유지합니다.
# DB confirmed 이후 write 장애에서는 Sheet 단독저장으로 우회하지 않습니다.
subprocess.run([sys.executable, 'scripts/patch_admin_operation_settings_dbfirst_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_admin_operation_settings_dbfirst_v1_20260908.py'], check=True)

"""
if "patch_admin_operation_settings_dbfirst_v1_20260908.py" not in canonical:
    anchor = '# 통합 인디게이터 하우스맨 오더 UI:'
    idx = canonical.find(anchor)
    if idx < 0:
        raise SystemExit('Canonical patcher anchor not found')
    canonical = canonical[:idx] + block + canonical[idx:]
    canonical_path.write_text(canonical, encoding='utf-8')

print('Admin operation settings DB-first patch applied.')
