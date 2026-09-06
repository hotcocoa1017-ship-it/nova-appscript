from pathlib import Path

MARKER = 'ROOM_UPLOAD_DB_FIRST_V2'
path = Path('09_RoomStatusUpload.js')
text = path.read_text(encoding='utf-8')


def replace_once(source, old, new, label):
    if old not in source:
        raise SystemExit(f'{label} anchor not found')
    return source.replace(old, new, 1)

if MARKER not in text:
    text = replace_once(
        text,
        """      const existingForTarget = {};\n      const keptRows = [];\n""",
        """      const existingForTarget = {};\n      const keptRows = [];\n      const dbFirstEnabled = typeof novaRoomUploadDbFirstEnabled_ === 'function' && novaRoomUploadDbFirstEnabled_(); // ROOM_UPLOAD_DB_FIRST_V2\n      let dbBundle = null;\n      let dbCurrentRows = [];\n      let dbCurrentVersion = 0;\n      if (dbFirstEnabled) {\n        dbBundle = novaRoomUploadDbBundle_(token, preview.businessDate, preview.site);\n        if (!dbBundle || dbBundle.ok === false) throw new Error('DB 최신 객실현황을 확인하지 못했습니다.');\n        dbCurrentRows = Array.isArray(dbBundle.currentRows) ? dbBundle.currentRows : [];\n        dbCurrentVersion = dbCurrentRows.reduce((max, row) => Math.max(max, Number(row && row['마지막변경버전'] || 0)), 0);\n      }\n""",
        'db bundle declaration'
    )

    text = replace_once(
        text,
        """      const version = resetExisting\n        ? reserveRoomUploadResetVersion_(preview.businessDate, preview.site)\n        : reserveDataVersion_({ lockHeld: true });\n""",
        """      if (dbFirstEnabled) {\n        // DB가 Sheet보다 최신일 수 있으므로 핵심 객실상태/배정값은 DB를 우선해 업로드 계산 기준을 맞춥니다.\n        dbCurrentRows.forEach(data => {\n          const roomNo = normalizeRoomNo_(data && data['객실번호']);\n          if (!roomNo) return;\n          const previous = existingForTarget[roomNo] || {};\n          existingForTarget[roomNo] = Object.assign({}, previous, {\n            '업무일자': String(data['업무일자'] || preview.businessDate).trim(),\n            '사업장': String(data['사업장'] || preview.site).trim(),\n            '객실번호': roomNo,\n            '동': String(data['동'] || previous['동'] || '').trim(),\n            '객실상태': String(data['객실상태'] || '').trim().toUpperCase(),\n            '청소상태': String(data['청소상태'] || '').trim().toUpperCase(),\n            '정비유형': String(data['정비유형'] || previous['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),\n            '배정유형': String(data['배정유형'] || previous['배정유형'] || '').trim().toUpperCase(),\n            '룸메이드사번': String(data['룸메이드사번'] || '').trim(),\n            '보조룸메이드사번': String(data['보조룸메이드사번'] || '').trim(),\n            'QM사번': String(data['QM사번'] || '').trim(),\n            '객실운영상태': String(data['객실운영상태'] || '').trim(),\n            '마지막변경버전': Number(data['마지막변경버전'] || 0),\n            '수정일시': String(data['수정일시'] || previous['수정일시'] || '').trim()\n          });\n        });\n      }\n\n      let version = dbFirstEnabled\n        ? reserveRoomUploadDbAlignedVersion_(dbCurrentVersion, resetExisting, preview.businessDate, preview.site)\n        : (resetExisting\n          ? reserveRoomUploadResetVersion_(preview.businessDate, preview.site)\n          : reserveDataVersion_({ lockHeld: true }));\n""",
        'version alignment'
    )

    text = replace_once(
        text,
        """      const currentWriteStartedMs = Date.now();\n""",
        """      let dbCommitMs = 0;\n      let dbCommit = null;\n      if (dbFirstEnabled) {\n        const dbCommitStartedMs = Date.now();\n        const dbRooms = buildRoomUploadDbRows_(newRows, headerMap);\n        dbCommit = novaRoomUploadDbApply_(token, {\n          businessDate: preview.businessDate,\n          site: preview.site,\n          rooms: dbRooms,\n          expectedVersion: dbCurrentVersion,\n          version,\n          requestId: `ROOM_UPLOAD_V2:${String(previewId || '').trim()}`,\n          upload: {\n            fileName: preview.fileName,\n            extension: preview.extension,\n            counts: preview.counts || {},\n            totalRooms: dbRooms.length,\n            roomsByStatus: buildUploadRoomsByStatus_(preview.statusByRoom),\n            applyMode: resetExisting ? 'RESET_REPLACE' : 'MERGE_REPLACE',\n            roommaidAssignment: {\n              sheetFound: Boolean(preview.roommaidAssignment && preview.roommaidAssignment.sheetFound),\n              requestedCount: Number(preview.roommaidAssignment && preview.roommaidAssignment.requestedCount || 0),\n              validCount: Number(preview.roommaidAssignment && preview.roommaidAssignment.validCount || 0),\n              appliedCount: appliedAssignments.length,\n              skippedCount: skippedAssignments.length,\n              appliedByEmployee: buildAppliedAssignmentSummary_(appliedAssignments)\n            }\n          }\n        });\n        dbCommitMs = Date.now() - dbCommitStartedMs;\n        const committedVersion = Number(dbCommit && dbCommit.version || 0);\n        if (!committedVersion) throw new Error('DB 업로드 확정 버전을 확인하지 못했습니다.');\n        if (committedVersion !== version) {\n          // 동일 previewId 재시도 시 DB는 기존 확정을 멱등 반환합니다. Sheet도 그 확정버전에 맞춥니다.\n          version = committedVersion;\n          const versionColumn = Number(headerMap['마지막변경버전'] || 0);\n          if (!versionColumn) throw new Error('현재객실현황 마지막변경버전 열을 찾을 수 없습니다.');\n          newRows.forEach(row => { row[versionColumn - 1] = version; });\n        }\n      }\n\n      const currentWriteStartedMs = Date.now();\n""",
        'db commit before sheet mirror'
    )

    text = replace_once(
        text,
        """        timing: {\n          totalMs: Date.now() - applyStartedMs,\n          lockWaitMs: lockAcquiredMs - lockRequestedMs,\n          currentWriteMs,\n          maintenanceMs,\n          flushMs,\n          roomWriteMode\n        },\n""",
        """        dbFirst: Boolean(dbFirstEnabled),\n        dbCommit: dbCommit ? {\n          version: Number(dbCommit.version || 0),\n          previousVersion: Number(dbCommit.previousVersion || 0),\n          idempotent: Boolean(dbCommit.idempotent),\n          requestId: String(dbCommit.requestId || '')\n        } : null,\n        timing: {\n          totalMs: Date.now() - applyStartedMs,\n          lockWaitMs: lockAcquiredMs - lockRequestedMs,\n          dbCommitMs,\n          currentWriteMs,\n          maintenanceMs,\n          flushMs,\n          roomWriteMode\n        },\n""",
        'response db-first metadata'
    )

    helper_anchor = "\n\nfunction reserveRoomUploadResetVersion_(businessDate, site)"
    helper = r'''

function reserveRoomUploadDbAlignedVersion_(dbCurrentVersion, resetExisting, businessDate, site) { // ROOM_UPLOAD_DB_FIRST_V2
  const dbVersion = Math.max(0, Number(dbCurrentVersion || 0));
  let reserved = resetExisting
    ? Number(reserveRoomUploadResetVersion_(businessDate, site) || 0)
    : Number(reserveDataVersion_({ lockHeld: true }) || 0);
  if (reserved > dbVersion) return reserved;

  // DB room version이 Apps Script 전역버전보다 앞선 경우 전역버전도 같이 전진시켜
  // 이후 Sheet/DB expectedVersion이 다시 어긋나지 않도록 합니다.
  reserved = dbVersion + 1;
  PropertiesService.getScriptProperties().setProperty('NOVA_DATA_VERSION', String(reserved));
  return reserved;
}

function buildRoomUploadDbRows_(rows, headerMap) { // ROOM_UPLOAD_DB_FIRST_V2
  return (rows || []).map(row => {
    const data = rowObjectFromValues_(row, headerMap);
    return {
      roomNo: String(data['객실번호'] || '').trim(),
      building: String(data['동'] || '').trim(),
      roomStatus: String(data['객실상태'] || '').trim().toUpperCase(),
      cleaningStatus: String(data['청소상태'] || 'WAITING').trim().toUpperCase(),
      cleaningType: String(data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
      assignmentType: String(data['배정유형'] || '').trim().toUpperCase(),
      roommaidEmployeeNo: String(data['룸메이드사번'] || '').trim(),
      secondaryRoommaidEmployeeNo: String(data['보조룸메이드사번'] || '').trim(),
      qmEmployeeNo: String(data['QM사번'] || '').trim(),
      operationalStatus: typeof normalizeIndicatorRoomOperationalStatus_ === 'function'
        ? normalizeIndicatorRoomOperationalStatus_(data['객실운영상태'])
        : String(data['객실운영상태'] || '').trim()
    };
  }).filter(row => row.roomNo);
}
'''
    if helper_anchor not in text:
        raise SystemExit('helper insertion anchor not found')
    text = text.replace(helper_anchor, helper + helper_anchor, 1)

# Hard guards
for required in [
    'ROOM_UPLOAD_DB_FIRST_V2',
    'novaRoomUploadDbBundle_',
    'novaRoomUploadDbApply_',
    'nova_room_upload_apply_v2' if False else 'buildRoomUploadDbRows_',
    'reserveRoomUploadDbAlignedVersion_',
    'dbCommitMs',
    'ROOM_UPLOAD_V2:'
]:
    if required not in text:
        raise SystemExit(f'missing marker: {required}')

# DB commit must appear before the first Sheet current-row write timer.
if text.index('novaRoomUploadDbApply_') > text.index('const currentWriteStartedMs = Date.now();'):
    raise SystemExit('DB commit is not before Sheet current write')

path.write_text(text, encoding='utf-8')
print('Applied ROOM_UPLOAD_DB_FIRST_V2: latest DB overlay -> DB commit -> Sheet mirror.')
