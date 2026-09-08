from pathlib import Path
import sys


def replace_once(text, old, new, label):
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 anchor, found {count}')
    return text.replace(old, new, 1)


bridge_path = Path('DbFirstBridge.js')
bridge = bridge_path.read_text(encoding='utf-8')
if "'nova_admin_code_settings_read_v1'" not in bridge:
    anchor = "    'nova_operation_settings_save_v1', // NOVA_OPERATION_SETTINGS_DB_FIRST_V1\n"
    insert = anchor + (
        "    'nova_admin_code_settings_read_v1', // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1\n"
        "    'nova_admin_code_settings_save_v1', // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1\n"
        "    'nova_admin_code_settings_disable_v1', // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1\n"
    )
    bridge = replace_once(bridge, anchor, insert, 'admin code RPC allowlist')
bridge_path.write_text(bridge, encoding='utf-8')

client_path = Path('Client.html')
client = client_path.read_text(encoding='utf-8')
client = replace_once(
    client,
    "callServer('saveAdminCodeRow', state.token, payload)",
    "callServer('saveAdminCodeRowDbFirst', state.token, Object.assign({}, payload, { requestId: novaRealtimeRequestId_('ADMIN_CODE_SAVE_V1', 'ADMIN') })) // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1",
    'admin code save client route'
)
client = replace_once(
    client,
    "callServer('disableAdminCodeRow', state.token, { group: state.settings.selectedGroup, code })",
    "callServer('disableAdminCodeRowDbFirst', state.token, { group: state.settings.selectedGroup, code, requestId: novaRealtimeRequestId_('ADMIN_CODE_DISABLE_V1', 'ADMIN') }) // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1",
    'admin code disable client route'
)
client_path.write_text(client, encoding='utf-8')

canonical_path = Path('scripts/fix_patch_site_scope_v2.py')
canonical = canonical_path.read_text(encoding='utf-8')
block = """
# 관리자 코드/명칭 중 안정형 8개 그룹은 PostgreSQL을 쓰기 권위로 사용하고 코드설정 Sheet는 호환 미러로 유지합니다.
# 사업장/객실타입/직무 자동시드는 기존 동작을 보존하며, QM 정의는 다음 컷오버로 분리합니다.
subprocess.run([sys.executable, 'scripts/patch_admin_code_settings_dbfirst_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_admin_code_settings_dbfirst_v1_20260908.py'], check=True)

"""
if 'patch_admin_code_settings_dbfirst_v1_20260908.py' not in canonical:
    anchor = '# 통합 인디게이터 하우스맨 오더 UI:'
    idx = canonical.find(anchor)
    if idx < 0:
        raise SystemExit('canonical admin-code anchor not found')
    canonical = canonical[:idx] + block + canonical[idx:]
    canonical_path.write_text(canonical, encoding='utf-8')

print('Admin code settings DB-first patch applied.')
