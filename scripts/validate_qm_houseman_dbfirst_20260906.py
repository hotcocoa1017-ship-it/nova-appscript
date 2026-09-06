from pathlib import Path
import sys

CLIENT = Path('Client.html')
MARKER = 'QM_HOUSEMAN_DBFIRST_V1'


def fail(message):
    print(f'ERROR: {message}', file=sys.stderr)
    raise SystemExit(97)


def require(text, needle, label):
    if needle not in text:
        fail(f'missing {label}')
    print(f'PASS: {label}')


def main():
    text = CLIENT.read_text(encoding='utf-8')

    if text.count(MARKER) < 3:
        fail(f'{MARKER} marker count too low: {text.count(MARKER)}')
    print(f'PASS: {MARKER} markers={text.count(MARKER)}')

    require(text, 'async function novaQmHousemanDbFirstRpc_(apiPayload)', 'QM direct RPC helper')
    require(text, '/rest/v1/rpc/nova_create_qm_houseman_order', 'QM RPC endpoint')
    require(text, "body: JSON.stringify({ p_payload: apiPayload })", 'RPC payload wrapper')
    require(text, "requestRole === 'QM'", 'QM direct route selector')
    require(text, 'await novaQmHousemanDbFirstRpc_(apiPayload)', 'QM direct RPC call')
    require(text, "await novaPublicHousemanDbFirstRpc_(apiPayload)", 'PUBLIC direct route preserved')
    require(text, "await novaRealtimeFetch_('/v1/houseman-orders'", 'ROOMMAID generic Cloud Run route preserved')
    require(text, "unknown.code = 'QM_HOUSEMAN_DB_RESULT_UNKNOWN'", 'ambiguous network fail-closed')
    require(text, "status === 404 && ['PGRST202', 'PGRST205'].includes(code)", 'legacy fallback only for missing RPC')
    require(text, 'if (!rpcUnavailable) throw error;', 'QM permission/validation errors do not fall back')
    require(text, "realtimeOrderId: realtime.orderId || realtime.order?.orderId || ''", 'Sheet mirror receives DB order id')
    require(text, 'const mirrorPromise = mirrorRoommaidHousemanRequestToSheet_(mirrorPayload);', 'Sheet mirror stays background')

    forbidden = "requestRole === 'QM'\n        ? await novaRealtimeFetch_('/v1/houseman-orders'"
    if forbidden in text:
        fail('QM is still routed directly to generic Cloud Run create endpoint')
    print('PASS: QM no longer uses generic create endpoint')

    print('QM_HOUSEMAN_DBFIRST_V1 validation PASS')


if __name__ == '__main__':
    main()
