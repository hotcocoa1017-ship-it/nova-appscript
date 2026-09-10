from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
client_path = ROOT / 'Client.html'
validator_path = ROOT / 'scripts/validate_room_upload_realtime_sync_20260907.py'
client = client_path.read_text(encoding='utf-8')
validator = validator_path.read_text(encoding='utf-8')

# No canonical path may fall back to the legacy Sheet-first mutation if V5 is unavailable.
old = """      if (error?.missingRpc) {
        console.warn('[NOVA Upload] V4 RPC missing before DB mutation · legacy fallback:', error?.message || error);
        try { sessionStorage.removeItem(stable.key); } catch (ignore) {}
        return callServer('applyRoomStatusUpload', state.token, previewId, { resetExisting: resetMode });
      }
"""
new = """      if (error?.missingRpc) {
        try { sessionStorage.removeItem(stable.key); } catch (ignore) {}
        throw new Error('객실업로드 V5 DB 안전경로를 사용할 수 없습니다. 데이터 보호를 위해 업로드를 중단합니다.'); // ROOM_UPLOAD_NO_LEGACY_FALLBACK_V1
      }
"""
if old in client:
    client = client.replace(old, new, 1)
elif '객실업로드 V5 DB 안전경로를 사용할 수 없습니다.' not in client:
    raise SystemExit('commit missing-RPC legacy fallback not found')

# Evolve the canonical Realtime upload validator to the V5 client route while preserving V4 server-plan checks.
validator = validator.replace("novaRoomUploadRpcV4_('nova_room_upload_apply_v4'", "novaRoomUploadRpcV4_('nova_room_upload_apply_v5'")
validator = validator.replace('atomic V4 commit', 'atomic V5 guarded commit')
validator = validator.replace('UI routed through V4', 'UI routed through guarded DB-first path')
validator = validator.replace('# Client order: DB snapshot -> legacy-rule prepare -> atomic V4 DB commit -> DB re-read -> Sheet mirror.', '# Client order: DB snapshot -> legacy-rule prepare -> guarded V5 DB commit -> DB re-read -> Sheet mirror.')

start = validator.find('# Fail-closed check without brittle regex escaping.')
end = validator.find('# Legacy apply remains untouched for compatibility before DB mutation.')
if start < 0 or end < 0 or end <= start:
    raise SystemExit('validator fail-closed section not found')
new_section = '''# Fail-closed check: the guarded commit path never falls back to Sheet-first.\ncommit_pos = client.index("committed = await novaRoomUploadRpcV4_('nova_room_upload_apply_v5'")\nafter_pos = client.index('if (!committed?.ok || committed?.dbFirst !== true)', commit_pos)\ncommit_window = client[commit_pos:after_pos]\nrequire(commit_window, 'if (error?.missingRpc)', 'explicit missing-RPC fail-closed branch')\nforbid(commit_window, "return callServer('applyRoomStatusUpload'", 'legacy mutation fallback inside guarded commit')\nrequire(commit_window, '객실업로드 V5 DB 안전경로를 사용할 수 없습니다.', 'V5 missing-RPC stop message')\nrequire(commit_window, '// 네트워크 결과불명/버전충돌/권한오류에서는 Sheet-first를 병행하지 않습니다.', 'fail-closed explanation')\nrequire(commit_window, 'throw error;', 'post-mutation errors rethrown')\n\n'''
validator = validator[:start] + new_section + validator[end:]
validator = validator.replace(
    "print('PASS: room upload DB-first V4 app bridge preserves legacy rules/side effects, commits DB before operational Sheet writes, uses exact per-room versions, fails closed on ambiguous results, and passes JS syntax checks.')",
    "print('PASS: room upload guarded V5 client + V4 app bridge preserve business rules, commit DB before Sheet writes, never fall back to Sheet-first, and pass JS syntax checks.')"
)

client_path.write_text(client, encoding='utf-8')
validator_path.write_text(validator, encoding='utf-8')
print('ROOM_UPLOAD_RELIABILITY_V5 follow-up patch applied')
