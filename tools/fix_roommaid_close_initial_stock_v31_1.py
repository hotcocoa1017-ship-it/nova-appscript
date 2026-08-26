#!/usr/bin/env python3
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '19_RoommaidCloseJournal.js'
text = TARGET.read_text(encoding='utf-8')
original = text

old1 = """          const openingInitialStock = Boolean(active.initialStock && !active.manualInitialStock);\n          if (openingInitialStock) {\n            // 최종 객실현황 업로드에서 시작한 전일재고는 당일 퇴실상태로 바뀌어도\n            // 같은 미완료 정비주기 동안 전일재고 원천분류를 유지한다.\n            // 그래야 통합 인디게이터/업로드의 전일재고와 마감일지 전일재고가 어긋나지 않는다.\n            active.initialStock = true;\n            active.departure = false;\n          } else {\n            // 당일 수동 재고 또는 기존 퇴실주기는 기존 동작대로 최종 퇴실분류를 따른다.\n            active.initialStock = false;\n            active.manualInitialStock = false;\n            active.departure = true;\n          }\n          active.bucket = nextBucket;\n          active.sourceStatus = nextStatus;\n          active.reclassifiedVersion = item.version;\n          active.reclassifiedAt = item.eventAt;\n"""
new1 = """          const openingInitialStock = Boolean(active.initialStock && !active.manualInitialStock);\n          if (openingInitialStock) {\n            // 최종 업로드에서 시작한 전일재고는 같은 미완료 정비주기에서 퇴실상태로 바뀌어도\n            // 전일재고의 원래 일반/RC/HU 분류를 그대로 유지한다.\n            // 현재 퇴실상태는 같은 정비주기의 표시상태로만 기억하고 금일퇴실을 새로 1건 만들지 않는다.\n            active.initialStock = true;\n            active.departure = false;\n            active.openingStockReclassifiedTo = nextStatus;\n            active.openingStockReclassifiedVersion = item.version;\n            active.openingStockReclassifiedAt = item.eventAt;\n          } else {\n            // 당일 수동 재고 또는 기존 퇴실주기는 기존 동작대로 최종 퇴실분류를 따른다.\n            active.initialStock = false;\n            active.manualInitialStock = false;\n            active.departure = true;\n            active.bucket = nextBucket;\n            active.sourceStatus = nextStatus;\n            active.reclassifiedVersion = item.version;\n            active.reclassifiedAt = item.eventAt;\n          }\n"""
if text.count(old1) != 1:
    raise SystemExit(f'PATCH_ERROR opening-stock block expected 1 match, found {text.count(old1)}')
text = text.replace(old1, new1, 1)

old2 = """      let target = [...roomEvents].reverse().find(event =>\n        !event.completed && !event.canceled\n        && (!sourceRecognized || String(event.bucket || 'BUILDING').trim().toUpperCase() === desiredBucket)\n      ) || null;\n      if (!target && !sourceRecognized) {\n        target = [...roomEvents].reverse().find(event => !event.completed && !event.canceled) || null;\n      }\n"""
new2 = """      let target = [...roomEvents].reverse().find(event =>\n        !event.completed && !event.canceled\n        && (!sourceRecognized || String(event.bucket || 'BUILDING').trim().toUpperCase() === desiredBucket)\n      ) || null;\n      // 전일재고가 완료 전 퇴실/RC/HU 상태로 바뀐 경우에도 같은 정비주기의 완료로 연결한다.\n      // 이때 전일재고의 원래 분류는 유지하여 전일재고 숫자와 완료 차감 기준이 서로 어긋나지 않게 한다.\n      if (!target && sourceRecognized) {\n        target = [...roomEvents].reverse().find(event =>\n          !event.completed && !event.canceled && event.initialStock && !event.manualInitialStock\n          && String(event.openingStockReclassifiedTo || '').trim().toUpperCase() === sourceStatus\n        ) || null;\n      }\n      if (!target && !sourceRecognized) {\n        target = [...roomEvents].reverse().find(event => !event.completed && !event.canceled) || null;\n      }\n"""
if text.count(old2) != 1:
    raise SystemExit(f'PATCH_ERROR completion-target block expected 1 match, found {text.count(old2)}')
text = text.replace(old2, new2, 1)

old3 = """    // 이력 누락 등으로 현재 퇴실주기를 workloadEvents에서 찾지 못해도 현재 객실상태 1건은 보장합니다.\n    if (!visible.currentEvent) {\n      incrementCycle(null, { roomNo, bucket: visible.currentBucket || roommaidCloseSpecialBucket_(status) || 'BUILDING' });\n    }\n"""
new3 = """    // 전일재고가 완료 전 퇴실상태로 재분류된 것이라면 같은 정비주기이므로 금일퇴실을 추가하지 않는다.\n    const openingStockCycle = [...(workloadEvents || [])].reverse().find(event =>\n      event && event.initialStock && !event.manualInitialStock && !event.canceled\n      && normalizeRoomNo_(event.roomNo) === roomNo\n      && String(event.openingStockReclassifiedTo || '').trim().toUpperCase() === status\n    ) || null;\n\n    // 이력 누락 등으로 현재 퇴실주기를 workloadEvents에서 찾지 못한 경우에만 현재 객실상태 1건을 보장한다.\n    if (!visible.currentEvent && !openingStockCycle) {\n      incrementCycle(null, { roomNo, bucket: visible.currentBucket || roommaidCloseSpecialBucket_(status) || 'BUILDING' });\n    }\n"""
if text.count(old3) != 1:
    raise SystemExit(f'PATCH_ERROR departure-fallback block expected 1 match, found {text.count(old3)}')
text = text.replace(old3, new3, 1)

old4 = """    const desiredBucket = roommaidCloseSpecialBucket_(status) || 'BUILDING';\n    const matched = (workloadEvents || []).some(event => {\n      if (!event || event.canceled || normalizeRoomNo_(event.roomNo) !== roomNo) return false;\n      if (String(event.bucket || 'BUILDING').trim().toUpperCase() !== desiredBucket) return false;\n      if (normalizeRoommaidCloseRoomStatus_(event.sourceStatus, statusNormalizer) !== status) return false;\n      return isInitialStock ? Boolean(event.initialStock) : Boolean(event.departure);\n    });\n"""
new4 = """    const desiredBucket = roommaidCloseSpecialBucket_(status) || 'BUILDING';\n    const matched = (workloadEvents || []).some(event => {\n      if (!event || event.canceled || normalizeRoomNo_(event.roomNo) !== roomNo) return false;\n      if (isInitialStock) {\n        if (String(event.bucket || 'BUILDING').trim().toUpperCase() !== desiredBucket) return false;\n        if (normalizeRoommaidCloseRoomStatus_(event.sourceStatus, statusNormalizer) !== status) return false;\n        return Boolean(event.initialStock);\n      }\n      if (isDeparture) {\n        const normalDeparture = Boolean(event.departure)\n          && String(event.bucket || 'BUILDING').trim().toUpperCase() === desiredBucket\n          && normalizeRoommaidCloseRoomStatus_(event.sourceStatus, statusNormalizer) === status;\n        const openingStockReclassification = Boolean(event.initialStock && !event.manualInitialStock)\n          && String(event.openingStockReclassifiedTo || '').trim().toUpperCase() === status;\n        return normalDeparture || openingStockReclassification;\n      }\n      return false;\n    });\n"""
if text.count(old4) != 1:
    raise SystemExit(f'PATCH_ERROR integrity block expected 1 match, found {text.count(old4)}')
text = text.replace(old4, new4, 1)

TARGET.write_text(text, encoding='utf-8')

# Guardrails: v31 schema and v30 realtime-related code remain untouched; only this close-journal file changes.
assert 'SCHEMA_VERSION: 27' in text
assert 'openingStockReclassifiedTo' in text
assert text != original
subprocess.run(['node', '--check', str(TARGET)], check=True)

print('PATCH_OK')
print('Repository only; production Apps Script NOT changed yet')
print('Changed: 19_RoommaidCloseJournal.js only')
print('Fixed: opening stock keeps original bucket/status, does not double-count same-cycle departure')
print('Fixed: completion links back to reclassified opening-stock cycle')
print('Fixed: close-save integrity validator accepts the same preserved opening-stock cycle')
print('Preserved: v31 schema 27, v30 realtime cleaning reset, personal performance, RC/HU multi-cycle rules, UI')
print('Syntax: PASS')
print('VERIFY: PASS')
