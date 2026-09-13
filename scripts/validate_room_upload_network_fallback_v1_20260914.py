from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
index = (ROOT / 'Index.html').read_text(encoding='utf-8')
server = (ROOT / 'RoomUploadNetworkFallback.js').read_text(encoding='utf-8')
client = (ROOT / 'RoomUploadNetworkFallbackClient.html').read_text(encoding='utf-8')
canonical = (ROOT / 'Client.html').read_text(encoding='utf-8')

allowed_paths = [
    '/rest/v1/rpc/nova_room_upload_state_v3',
    '/rest/v1/rpc/nova_room_upload_apply_v5',
    '/rest/v1/rpc/nova_room_upload_mark_stage_v1',
]

checks = {
    'index include': "include_('RoomUploadNetworkFallbackClient')" in index,
    'marker': 'ROOM_UPLOAD_NETWORK_FALLBACK_V1' in server and 'ROOM_UPLOAD_NETWORK_FALLBACK_V1' in client,
    'fixed project origin server': "https://evoetxfjmkkjptucwxsv.supabase.co" in server,
    'fixed project origin client': "https://evoetxfjmkkjptucwxsv.supabase.co" in client,
    'server only post': "method !== 'POST'" in server and "method: 'post'" in server,
    'server no redirects': 'followRedirects: false' in server,
    'server https validation': 'validateHttpsCertificates: true' in server,
    'server auth forwarding': 'Authorization: authorization' in server and 'apikey: apiKey' in server,
    'client native first': 'return await nativeFetch(input, init)' in client,
    'client fallback in catch': 'catch (error)' in client and 'return proxyFetch_(targetUrl, input, init || {}, error)' in client,
    'apps script bridge only fallback': '.novaRoomUploadFetchProxyV1(payload)' in client,
    'synthetic response preserves status': 'status: Number(result.status)' in client,
    'canonical V5 retained': "novaRoomUploadRpcV4_('nova_room_upload_apply_v5'" in canonical,
    'canonical no sheet-first fallback': canonical.count('ROOM_UPLOAD_NO_LEGACY_FALLBACK_V1') >= 2,
}

for path in allowed_paths:
    checks[f'server allows {path}'] = path in server
    checks[f'client targets {path}'] = path in client

# The bridge must not become a generic URL proxy.
checks['server allowlist cardinality'] = server.count("'/rest/v1/rpc/nova_room_upload_") == 3
checks['client allowlist cardinality'] = client.count("'/rest/v1/rpc/nova_room_upload_") == 3
checks['no service-role exposure'] = 'SERVICE_ROLE' not in server.upper() and 'SERVICE_ROLE' not in client.upper()

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(('PASS' if ok else 'FAIL'), name)
if failed:
    raise SystemExit('ROOM_UPLOAD_NETWORK_FALLBACK_V1 failed: ' + ', '.join(failed))
print(f'ROOM_UPLOAD_NETWORK_FALLBACK_V1 PASS ({len(checks)}/{len(checks)})')
