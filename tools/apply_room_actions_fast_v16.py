#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "06_Indicator.js"


def fail(message):
    print(f"PATCH_ERROR: {message}")
    sys.exit(1)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


if not TARGET.exists():
    fail("06_Indicator.js not found")

text = TARGET.read_text(encoding="utf-8")
original = text

# 1) Do not load the whole user index for room-status / flags / clear operations.
text = replace_once(
    text,
    """    const userIndex = getUserIndex_();\n    const writeLockRequestedMs = Date.now();""",
    """    // 직원 검증이 필요한 배정 작업에서만 사용자 전체 인덱스를 읽는다.\n    // 객실상태·운영표시·배정초기화 등은 불필요한 사용자 조회를 건너뛰어 저장 응답을 단축한다.\n    const needsUserIndex = action === 'ASSIGN_ROOMMAID' || action === 'QM_ASSIGN';\n    const userIndex = needsUserIndex ? getUserIndex_() : null;\n    const writeLockRequestedMs = Date.now();""",
    "lazy user index"
)

# 2) Existing client already applies names/visual state optimistically. Return only authoritative core fields,
#    avoiding a second user-index dependency after the Sheet write.
text = replace_once(
    text,
    """    const responseRoom = currentRoomObject_(refreshed, rowNumber, {}, userIndex.byEmployeeNo);""",
    """    // Client가 이미 즉시 반영한 이름·표시정보는 유지하고, 서버에서 확정된 핵심 필드만 반환한다.\n    // 이로써 상태변경·운영표시 등에서 응답 직전 사용자 전체 인덱스 재의존을 제거한다.\n    const responseRoom = {\n      rowNumber,\n      businessDate,\n      site: String(refreshed['사업장'] || site).trim(),\n      roomNo,\n      roomStatus: String(refreshed['객실상태'] || '').trim(),\n      displayBaseRoomStatus: resolveIndicatorDisplayBaseRoomStatus_(refreshed),\n      cleaningStatus: String(refreshed['청소상태'] || '').trim(),\n      cleaningType: String(refreshed['정비유형'] || '').trim() || NOVA.CLEANING_TYPES.NORMAL,\n      assignmentType: String(refreshed['배정유형'] || '').trim() || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO,\n      roommaidEmployeeNo: String(refreshed['룸메이드사번'] || '').trim(),\n      secondaryRoommaidEmployeeNo: String(refreshed['보조룸메이드사번'] || '').trim(),\n      qmEmployeeNo: String(refreshed['QM사번'] || '').trim(),\n      preassigned: normalizeYesNo_(refreshed['선배정여부']) === 'Y',\n      vip: normalizeYesNo_(refreshed['VIP여부']) === 'Y',\n      importantRoom: normalizeYesNo_(refreshed['중요객실여부']) === 'Y',\n      operationalStatus: normalizeIndicatorRoomOperationalStatus_(refreshed[indicatorRoomOperationalStatusHeader_()]),\n      updatedAt: String(refreshed['수정일시'] || '').trim(),\n      version: Number(refreshed['마지막변경버전'] || version || 0)\n    };""",
    "partial authoritative response"
)

# 3) Move ASSIGN_ROOMMAID / QM_ASSIGN Telegram queue work out of the synchronous save path.
start_marker = "      try {\n        if (action === 'ASSIGN_ROOMMAID' && assignmentUser) {"
end_marker = "      } catch (notificationError) {\n        console.error(`객실작업 텔레그램 큐 등록 실패: ${notificationError && notificationError.message || notificationError}`);\n      }\n"
start = text.find(start_marker)
if start < 0:
    fail("synchronous notification block start not found")
end = text.find(end_marker, start)
if end < 0:
    fail("synchronous notification block end not found")
end += len(end_marker)
text = text[:start] + "      // 배정/QM 알림은 저장 성공 응답 후 Client가 비동기로 큐 등록한다.\n" + text[end:]

# 4) Deferred queue processor: add ASSIGN_ROOMMAID and QM_ASSIGN while preserving existing queue functions.
queue_anchor = """    const usersByEmployeeNo = getUserIndex_().byEmployeeNo;\n    const roommaidUsers = uniqueRoomOperationEmployeeNos_(safe.roommaidEmployeeNos)"""
queue_insert = """    const usersByEmployeeNo = getUserIndex_().byEmployeeNo;\n\n    if (action === 'ASSIGN_ROOMMAID') {\n      const primaryEmployeeNo = String(safe.primaryEmployeeNo || '').trim();\n      const secondaryEmployeeNo = String(safe.secondaryEmployeeNo || '').trim();\n      const primaryUser = primaryEmployeeNo ? usersByEmployeeNo[primaryEmployeeNo] || null : null;\n      const secondaryUser = secondaryEmployeeNo ? usersByEmployeeNo[secondaryEmployeeNo] || null : null;\n      if (!primaryUser || !primaryUser.enabled || String(primaryUser.role || '').trim().toUpperCase() !== 'ROOMMAID') {\n        return { ok: true, queued: false, count: 0, reason: 'ROOMMAID_NOT_AVAILABLE' };\n      }\n      const telegramBase = {\n        businessDate, site, roomNo,\n        roomStatus: String(safe.roomStatus || '').trim(),\n        cleaningType: String(safe.cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),\n        cleaningStatus: String(safe.cleaningStatus || 'ASSIGNED').trim().toUpperCase(),\n        assignmentType: String(safe.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),\n        preassigned: Boolean(safe.preassigned),\n        vip: Boolean(safe.vip),\n        importantRoom: Boolean(safe.importantRoom),\n        registeredBy: user.employeeNo,\n        version: Number(safe.version || 0)\n      };\n      let queuedCount = 0;\n      const first = queueCleaningAssignmentTelegram_(Object.assign({}, telegramBase, {\n        targetUser: primaryUser, assignmentRole: 'PRIMARY'\n      }));\n      if (first && first.queued) queuedCount += 1;\n      if (secondaryEmployeeNo && secondaryUser && secondaryUser.enabled\n          && String(secondaryUser.role || '').trim().toUpperCase() === 'ROOMMAID') {\n        const second = queueCleaningAssignmentTelegram_(Object.assign({}, telegramBase, {\n          targetUser: secondaryUser, assignmentRole: 'SECONDARY'\n        }));\n        if (second && second.queued) queuedCount += 1;\n      }\n      return { ok: true, queued: queuedCount > 0, count: queuedCount, reason: queuedCount ? '' : 'TELEGRAM_NOT_QUEUED' };\n    }\n\n    if (action === 'QM_ASSIGN') {\n      const qmEmployeeNo = String(safe.qmEmployeeNo || '').trim();\n      const qmUser = qmEmployeeNo ? usersByEmployeeNo[qmEmployeeNo] || null : null;\n      if (!qmUser || !qmUser.enabled || String(qmUser.role || '').trim().toUpperCase() !== 'QM') {\n        return { ok: true, queued: false, count: 0, reason: 'QM_NOT_AVAILABLE' };\n      }\n      const result = queueQmAssignmentTelegram_({\n        businessDate, site, roomNo, targetUser: qmUser,\n        preassigned: Boolean(safe.preassigned),\n        vip: Boolean(safe.vip),\n        importantRoom: Boolean(safe.importantRoom),\n        registeredBy: user.employeeNo,\n        version: Number(safe.version || 0)\n      });\n      return roomOperationDeferredQueueResult_(result);\n    }\n\n    const roommaidUsers = uniqueRoomOperationEmployeeNos_(safe.roommaidEmployeeNos)"""
text = replace_once(text, queue_anchor, queue_insert, "deferred queue handlers")

# 5) Deferred payload builder: create payloads for assignment and QM assignment.
builder_anchor = """  if (event === 'CLEAR_ASSIGNMENT') {"""
builder_insert = """  if (event === 'ASSIGN_ROOMMAID') {\n    const primaryEmployeeNo = String(current['룸메이드사번'] || '').trim();\n    const secondaryEmployeeNo = String(current['보조룸메이드사번'] || '').trim();\n    if (!primaryEmployeeNo) return null;\n    return Object.assign({}, common, {\n      action: 'ASSIGN_ROOMMAID',\n      primaryEmployeeNo,\n      secondaryEmployeeNo,\n      roomStatus: String(current['객실상태'] || '').trim(),\n      cleaningStatus: String(current['청소상태'] || 'ASSIGNED').trim().toUpperCase(),\n      cleaningType: String(current['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),\n      assignmentType: String(current['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),\n      preassigned: normalizeYesNo_(current['선배정여부']) === 'Y',\n      vip: normalizeYesNo_(current['VIP여부']) === 'Y',\n      importantRoom: normalizeYesNo_(current['중요객실여부']) === 'Y'\n    });\n  }\n\n  if (event === 'QM_ASSIGN') {\n    const qmEmployeeNo = String(current['QM사번'] || '').trim();\n    if (!qmEmployeeNo) return null;\n    return Object.assign({}, common, {\n      action: 'QM_ASSIGN',\n      qmEmployeeNo,\n      preassigned: normalizeYesNo_(current['선배정여부']) === 'Y',\n      vip: normalizeYesNo_(current['VIP여부']) === 'Y',\n      importantRoom: normalizeYesNo_(current['중요객실여부']) === 'Y'\n    });\n  }\n\n  if (event === 'CLEAR_ASSIGNMENT') {"""
text = replace_once(text, builder_anchor, builder_insert, "deferred payload builders")

if text == original:
    fail("no changes produced")

backup = TARGET.with_suffix(".js.backup_v15_before_room_fast")
if not backup.exists():
    backup.write_text(original, encoding="utf-8")
TARGET.write_text(text, encoding="utf-8")

# Guard rails: syntax and whitespace checks before creating a commit.
subprocess.run(["node", "--check", str(TARGET)], cwd=ROOT, check=True)
subprocess.run(["git", "diff", "--check", "--", "06_Indicator.js"], cwd=ROOT, check=True)

print("PATCH_OK")
print("Modified: 06_Indicator.js only")
print("Preserved: Client.html / UI / existing room-state rules / history / notification functions")
print("Changed: lazy user-index read + partial response + ASSIGN/QM Telegram post-save deferral")
subprocess.run(["git", "diff", "--stat", "--", "06_Indicator.js"], cwd=ROOT, check=True)
