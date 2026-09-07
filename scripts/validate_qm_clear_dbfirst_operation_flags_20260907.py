from pathlib import Path
import sys

CLIENT = Path('Client.html').read_text(encoding='utf-8')
REALTIME = Path('RealtimeDailySync.js').read_text(encoding='utf-8')
INDICATOR = Path('06_Indicator.js').read_text(encoding='utf-8')


def require(text, needle, label):
    if needle not in text:
        print(f'ERROR: missing {label}: {needle}', file=sys.stderr)
        sys.exit(92)


def forbid(text, needle, label):
    if needle in text:
        print(f'ERROR: forbidden {label}: {needle}', file=sys.stderr)
        sys.exit(93)


# 1) QM_CLEAR must be a DB-first Realtime action, using the dedicated RPC.
require(CLIENT, 'QM_CLEAR_DB_FIRST_V2', 'QM_CLEAR DB-first marker')
require(CLIENT, "'QM_ASSIGN', 'QM_CLEAR', 'QM_START'", 'QM_CLEAR Realtime routing')
require(CLIENT, '/rest/v1/rpc/nova_qm_clear_v1', 'QM_CLEAR Supabase RPC')
require(CLIENT, "p_request_id: requestId", 'QM_CLEAR idempotent request id')
require(CLIENT, "error.code = 'QM_CLEAR_DB_RESULT_UNKNOWN'", 'unknown-result protection')
require(CLIENT, "if (mappedAction === 'QM_CLEAR')", 'QM_CLEAR direct branch')
require(CLIENT, "if (directResult?.legacyFallback)", 'safe pre-mutation legacy fallback')
require(CLIENT, "directResult.message = directResult.message || 'QM 배정을 초기화했습니다.'", 'QM_CLEAR result message')

# A network-unknown direct result must never be converted into a Sheet-first fallback.
forbid(CLIENT, "QM_CLEAR_DB_RESULT_UNKNOWN') return callServer", 'unsafe QM_CLEAR fallback after unknown result')

# 2) DB event mirror must restore legacy Sheet/current-room/history compatibility.
require(REALTIME, 'QM_CLEAR_EVENT_MIRROR_V2', 'QM_CLEAR event mirror marker')
require(REALTIME, "if (action === 'QM_CLEAR')", 'QM_CLEAR event branch')
require(REALTIME, "'QM사번': ''", 'QM_CLEAR Sheet QM clear')
require(REALTIME, "'청소상태': 'COMPLETED'", 'QM_CLEAR Sheet status')
require(REALTIME, "status: 'QM_CLEAR'", 'QM_CLEAR unified history')
require(REALTIME, 'previousQmEmployeeNo', 'QM_CLEAR previous QM attribution')
require(REALTIME, 'alreadyApplied.add(requestId)', 'Realtime request dedup')

# 3) The three independent operation flags must survive periodic Sheets -> DB sync.
require(REALTIME, 'ROOM_OPERATION_FLAGS_FORWARD_SYNC_V2', 'operation flags forward sync marker')
require(REALTIME, "preassigned: map['선배정여부'] !== undefined", 'preassigned forward payload')
require(REALTIME, "vip: map['VIP여부'] !== undefined", 'VIP forward payload')
require(REALTIME, "importantRoom: map['중요객실여부'] !== undefined", 'important-room forward payload')
require(REALTIME, "if (action === 'UPDATE_OPERATION_FLAGS')", 'operation flags event mirror')
require(REALTIME, "'선배정여부': preassigned ? 'Y' : 'N'", 'preassigned Sheet mirror')
require(REALTIME, "'VIP여부': vip ? 'Y' : 'N'", 'VIP Sheet mirror')
require(REALTIME, "'중요객실여부': importantRoom ? 'Y' : 'N'", 'important-room Sheet mirror')

# 4) Preserve the legacy safety rule as a fallback guard too.
require(INDICATOR, "if (previousCleaningStatus !== 'QM_WAITING')", 'legacy QM_CLEAR state guard')
require(INDICATOR, "updates['QM사번'] = ''", 'legacy QM clear assignment behavior')
require(INDICATOR, "updates['청소상태'] = 'COMPLETED'", 'legacy QM clear completion state')

print('QM_CLEAR DB-first + operation flags regression gate passed.')
