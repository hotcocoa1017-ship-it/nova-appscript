/**
 * 객실현황 파일 업로드: XLSX/XLS/CSV/PDF 미리보기 후 일괄 반영
 */
const NOVA_ROOM_UPLOAD = Object.freeze({
  CACHE_PREFIX: 'NOVA_ROOM_UPLOAD_',
  CACHE_SECONDS: 3600,
  PREVIEW_STORE_SHEET: 'NOVA_업로드미리보기_임시',
  PREVIEW_STORE_TTL_MS: 60 * 60 * 1000,
  PREVIEW_STORE_CHUNK_CHARS: 40000,
  MAX_FILE_BYTES: 5 * 1024 * 1024,
  ROOMMAID_ASSIGNMENT_SHEET: '룸메이드 객실배정',
  STATUS_SHEETS: Object.freeze([
    { sheetName: '재고', code: 'STOCK', label: '재고' },
    { sheetName: '재고RC', code: 'STOCK_RC', label: '재고 R/C' },
    { sheetName: '재고HU', code: 'STOCK_HU', label: '재고 H/U' },
    { sheetName: '투숙', code: 'STAY', label: '투숙' },
    { sheetName: '퇴실예정', code: 'DUE_OUT', label: '퇴실예정' },
    { sheetName: '퇴실', code: 'CHECKED_OUT', label: '퇴실' },
    { sheetName: '재입실', code: 'RECHECKIN', label: '재입실' }
  ])
});

function previewRoomStatusUpload(formObject) { // (객실현황 파일 분석 및 미리보기)
  return measureResponse_('previewRoomStatusUpload', () => {
    const form = formObject || {};
    const user = requireRole_(String(form.token || ''), ['ADMIN', 'ORDER']);
    const businessDate = normalizeBusinessDate_(form.businessDate);
    const site = String(form.site || '').trim();
    const fileBlob = form.uploadFile;

    if (!site) throw new Error('업로드할 사업장을 먼저 선택하세요.');
    if (!fileBlob || typeof fileBlob.getBytes !== 'function') throw new Error('업로드할 파일을 선택하세요.');
    if (fileBlob.getBytes().length > NOVA_ROOM_UPLOAD.MAX_FILE_BYTES) throw new Error('업로드 파일은 5MB 이하만 가능합니다.');

    const master = getActiveRoomMasterForSite_(site);
    if (!master.rooms.length) throw new Error(`객실마스터에 ${site} 사용 객실이 없습니다.`);

    const fileName = String(fileBlob.getName() || '객실현황').trim();
    const extension = getFileExtension_(fileName);
    const parsed = parseRoomUploadBlob_(fileBlob, extension, master);
    const validation = validateRoomUpload_(parsed, master);
    const roommaidAssignment = normalizeRoommaidUploadAssignment_(parsed.roommaidAssignment);
    const assignmentWarnings = buildRoommaidAssignmentPreviewWarnings_(roommaidAssignment);
    const previewId = Utilities.getUuid();
    const payload = {
      employeeNo: user.employeeNo,
      businessDate,
      site,
      fileName,
      extension,
      createdAt: Date.now(),
      masterSignature: master.signature,
      statusByRoom: parsed.statusByRoom,
      counts: validation.counts,
      sourceHeadings: parsed.sourceHeadings || [],
      roommaidAssignment: {
        sheetFound: roommaidAssignment.sheetFound,
        byRoom: compactRoommaidAssignmentByRoom_(roommaidAssignment.byRoom),
        requestedCount: roommaidAssignment.requestedCount,
        validCount: roommaidAssignment.validCount,
        employeeCount: roommaidAssignment.employeeCount
      }
    };

    if (validation.canApply) saveRoomUploadPreview_(previewId, payload);

    return {
      ok: true,
      previewId: validation.canApply ? previewId : '',
      canApply: validation.canApply,
      fileName,
      businessDate,
      site,
      totalMasterRooms: master.rooms.length,
      matchedRooms: validation.matchedRooms,
      vacantCleanRooms: validation.counts.VACANT_CLEAN || 0,
      counts: NOVA_ROOM_UPLOAD.STATUS_SHEETS.map(def => ({
        code: def.code,
        label: def.label,
        sheetName: def.sheetName,
        count: validation.counts[def.code] || 0
      })),
      missingSheets: validation.missingSheets,
      duplicateRooms: validation.duplicateRooms,
      resolvedOverlapCount: validation.resolvedOverlapCount || 0,
      unknownRooms: validation.unknownRooms,
      warnings: validation.warnings.concat(assignmentWarnings),
      roommaidAssignment: {
        sheetFound: roommaidAssignment.sheetFound,
        requestedCount: roommaidAssignment.requestedCount,
        validCount: roommaidAssignment.validCount,
        employeeCount: roommaidAssignment.employeeCount,
        errorCount: roommaidAssignment.errors.length,
        warningCount: roommaidAssignment.warnings.length,
        errors: roommaidAssignment.errors,
        warnings: roommaidAssignment.warnings
      },
      message: validation.canApply
        ? (roommaidAssignment.sheetFound
          ? `검증이 완료되었습니다. 객실현황은 정상 반영 가능하며, ${NOVA_ROOM_UPLOAD.ROOMMAID_ASSIGNMENT_SHEET} 시트의 유효 배정 ${roommaidAssignment.validCount}실도 함께 반영됩니다.`
          : '검증이 완료되었습니다. 최종 반영을 누르면 현재객실현황이 갱신됩니다.')
        : '검증 오류가 있어 반영할 수 없습니다. 파일을 수정한 후 다시 업로드하세요.'
    };
  });
}

function applyRoomStatusUpload(token, previewId, options) { // (검증된 객실현황 최종 반영·초기화 후 교체)
  return measureResponse_('applyRoomStatusUpload', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safeOptions = options || {};
    const resetExisting = safeOptions.resetExisting === true;
    const preview = loadRoomUploadPreview_(previewId);
    if (!preview) throw new Error('업로드 미리보기가 만료되었습니다. 파일을 다시 선택하세요.');
    if (preview.employeeNo !== user.employeeNo) throw new Error('다른 사용자가 만든 업로드 미리보기입니다.');

    const master = getActiveRoomMasterForSite_(preview.site);
    if (master.signature !== preview.masterSignature) {
      throw new Error('미리보기 이후 객실마스터가 변경되었습니다. 파일을 다시 검증하세요.');
    }

    const lock = acquireWriteLock_(30000);
    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const headerMap = getHeaderMap_(sheet);
      const lastColumn = sheet.getLastColumn();
      const existingRows = sheet.getLastRow() > 1
        ? sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).getValues()
        : [];
      const existingForTarget = {};
      const keptRows = [];
      let removedTargetRowCount = 0;

      existingRows.forEach(row => {
        const data = rowObjectFromValues_(row, headerMap);
        const isTarget = String(data['업무일자'] || '').trim() === preview.businessDate
          && String(data['사업장'] || '').trim() === preview.site;
        if (isTarget) {
          removedTargetRowCount += 1;
          const roomNo = normalizeRoomNo_(data['객실번호']);
          if (roomNo) existingForTarget[roomNo] = data;
        } else {
          keptRows.push(row);
        }
      });

      const version = resetExisting
        ? reserveRoomUploadResetVersion_(preview.businessDate, preview.site)
        : reserveDataVersion_({ lockHeld: true });
      const updatedAt = nowText_();
      const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
      const requestedAssignments = normalizeRoommaidUploadAssignment_(preview.roommaidAssignment).byRoom;
      const appliedAssignments = [];
      const skippedAssignments = [];
      const departureConfirmedAssignments = [];
      const newRows = master.rooms.map(room => {
        const uploadedRoomStatus = preview.statusByRoom[room.roomNo] || 'VACANT_CLEAN';
        const existingRoom = existingForTarget[room.roomNo] || {};
        const previous = resetExisting ? {} : existingRoom;
        const roomStatus = resolveEffectiveUploadRoomStatus_(uploadedRoomStatus, previous);
        const baseOperation = enforceUploadRoomOperationState_(roomStatus, resolveUploadOperationState_(roomStatus, previous));
        const assignmentResolution = resolveUploadedRoommaidAssignment_(
          room.roomNo,
          roomStatus,
          previous,
          baseOperation,
          requestedAssignments[room.roomNo],
          usersByEmployeeNo
        );
        const operation = resetExisting && !assignmentResolution.applied
          ? baseOperation
          : assignmentResolution.operation;
        if (assignmentResolution.applied) appliedAssignments.push(assignmentResolution.assignment);
        if (assignmentResolution.skipped) skippedAssignments.push(assignmentResolution.skipped);
        const departureConfirmedAssignment = buildUploadDepartureConfirmedAssignment_(
          room.roomNo, existingRoom, roomStatus, operation, resetExisting
        );
        if (departureConfirmedAssignment) departureConfirmedAssignments.push(departureConfirmedAssignment);
        return rowFromHeaderMap_(lastColumn, headerMap, {
          '업무일자': preview.businessDate,
          '객실번호': room.roomNo,
          '사업장': room.site,
          '객실상태': roomStatus,
          '마지막객실상태': resolveIndicatorLastRoomStatusForUpload_(uploadedRoomStatus, roomStatus, previous),
          '이전객실상태': String(previous['이전객실상태'] || '').trim(),
          '이전청소상태': String(previous['이전청소상태'] || '').trim(),
          '이전룸메이드사번': String(previous['이전룸메이드사번'] || '').trim(),
          '이전보조룸메이드사번': String(previous['이전보조룸메이드사번'] || '').trim(),
          '청소상태': operation.cleaningStatus,
          '정비유형': operation.cleaningType,
          '배정유형': operation.assignmentType,
          '룸메이드사번': operation.roommaidEmployeeNo,
          '보조룸메이드사번': operation.secondaryRoommaidEmployeeNo,
          'QM사번': operation.qmEmployeeNo,
          '마지막변경버전': version,
          '수정일시': updatedAt,
          '동': room.building,
          '하우스맨상태': String(existingRoom['하우스맨상태'] || '').trim(),
          '하우스맨미완료수': Number(existingRoom['하우스맨미완료수'] || 0),
          '객실운영상태': typeof normalizeIndicatorRoomOperationalStatus_ === 'function'
            ? normalizeIndicatorRoomOperationalStatus_(existingRoom['객실운영상태'])
            : String(existingRoom['객실운영상태'] || '').trim()
        });
      });

      if (resetExisting) {
        assertResetRoomUploadAssignments_(newRows, headerMap, appliedAssignments);
      }

      const allRows = keptRows.concat(newRows);
      if (sheet.getLastRow() > 1) {
        sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).clearContent();
      }
      if (allRows.length) {
        ensureSheetRowCapacity_(sheet, allRows.length + 1);
        sheet.getRange(2, 1, allRows.length, lastColumn).setValues(allRows);
      }
      const maintenanceReset = resetExisting
        ? resetRoomMaintenanceHistoryForUpload_(preview.businessDate, preview.site, updatedAt)
        : createRoomMaintenanceResetSummary_();
      SpreadsheetApp.flush();
      publishDataVersion_(version, {
        domains: resetExisting ? ['ROOM', 'REPORT'] : ['ROOM'],
        businessDate: preview.businessDate,
        site: preview.site,
        lockHeld: true
      });

      appendUnifiedHistory_({
        recordType: NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD,
        businessDate: preview.businessDate,
        site: preview.site,
        roomNo: '',
        targetEmployeeNo: '',
        status: 'APPLIED',
        detail: {
          fileName: preview.fileName,
          extension: preview.extension,
          counts: preview.counts,
          totalRooms: newRows.length,
          roomStatusSchema: 1,
          applyMode: resetExisting ? 'RESET_REPLACE' : 'MERGE_REPLACE',
          removedTargetRowCount,
          maintenanceReset,
          roomsByStatus: buildUploadRoomsByStatus_(preview.statusByRoom),
          roommaidAssignment: {
            sheetFound: Boolean(preview.roommaidAssignment && preview.roommaidAssignment.sheetFound),
            requestedCount: Number(preview.roommaidAssignment && preview.roommaidAssignment.requestedCount || 0),
            validCount: Number(preview.roommaidAssignment && preview.roommaidAssignment.validCount || 0),
            appliedCount: appliedAssignments.length,
            skippedCount: skippedAssignments.length,
            appliedByEmployee: buildAppliedAssignmentSummary_(appliedAssignments)
          }
        },
        registeredBy: user.employeeNo,
        version
      });

      const assignmentPostWarnings = [];
      if (appliedAssignments.length) {
        try {
          appendRoomUploadAssignmentHistory_(appliedAssignments, {
            businessDate: preview.businessDate,
            site: preview.site,
            fileName: preview.fileName,
            registeredBy: user.employeeNo,
            registeredAt: updatedAt,
            version
          });
        } catch (error) {
          assignmentPostWarnings.push(`룸메이드 배정 업무이력 기록 실패: ${error.message}`);
        }
        assignmentPostWarnings.push(...queueRoomUploadAssignmentTelegrams_(appliedAssignments, {
          businessDate: preview.businessDate,
          site: preview.site,
          registeredBy: user.employeeNo,
          version,
          usersByEmployeeNo
        }));
      }
      if (departureConfirmedAssignments.length) {
        assignmentPostWarnings.push(...queueRoomUploadDepartureConfirmedTelegrams_(departureConfirmedAssignments, {
          businessDate: preview.businessDate,
          site: preview.site,
          registeredBy: user.employeeNo,
          version,
          usersByEmployeeNo
        }));
      }

      const roomObjects = newRows.map((row, index) => currentRoomObject_(
        rowObjectFromValues_(row, headerMap),
        keptRows.length + index + 2,
        {},
        usersByEmployeeNo
      ));

      removeRoomUploadPreview_(previewId, true);
      return {
        ok: true,
        version,
        businessDate: preview.businessDate,
        site: preview.site,
        totalRooms: newRows.length,
        counts: preview.counts,
        rooms: roomObjects,
        roommaidAssignment: {
          sheetFound: Boolean(preview.roommaidAssignment && preview.roommaidAssignment.sheetFound),
          requestedCount: Number(preview.roommaidAssignment && preview.roommaidAssignment.requestedCount || 0),
          appliedCount: appliedAssignments.length,
          skippedCount: skippedAssignments.length,
          skipped: skippedAssignments,
          warnings: assignmentPostWarnings
        },
        resetExisting,
        removedTargetRowCount,
        maintenanceReset,
        message: buildRoomStatusUploadApplyMessage_(preview, newRows.length, appliedAssignments.length, skippedAssignments.length, resetExisting, removedTargetRowCount, maintenanceReset)
      };
    } finally {
      lock.releaseLock();
    }
  });
}


function reserveRoomUploadResetVersion_(businessDate, site) { // (초기화 재업로드 ROOM·REPORT 동기화버전 강제 전진)
  const currentSyncVersion = Number(getSyncVersion_(['ROOM', 'REPORT'], businessDate, site) || 0);
  const reservedVersion = Number(reserveDataVersion_({ lockHeld: true }) || 0);
  if (reservedVersion > currentSyncVersion) return reservedVersion;

  const nextVersion = currentSyncVersion + 1;
  PropertiesService.getScriptProperties().setProperty('NOVA_DATA_VERSION', String(nextVersion));
  return nextVersion;
}

function assertResetRoomUploadAssignments_(newRows, headerMap, appliedAssignments) { // (초기화 재업로드 최종 배정이 이번 업로드 배정과 정확히 일치하는지 검증)
  const expectedByRoom = {};
  (appliedAssignments || []).forEach(item => {
    const roomNo = normalizeRoomNo_(item && item.roomNo);
    if (!roomNo) return;
    expectedByRoom[roomNo] = {
      primaryEmployeeNo: String(item.primaryEmployeeNo || item.employeeNo || '').trim(),
      secondaryEmployeeNo: String(item.secondaryEmployeeNo || '').trim(),
      assignmentType: String(item.assignmentType || soloAssignmentTypeCode_()).trim().toUpperCase()
    };
  });

  const roomColumn = headerMap['객실번호'];
  const cleaningStatusColumn = headerMap['청소상태'];
  const assignmentTypeColumn = headerMap['배정유형'];
  const primaryColumn = headerMap['룸메이드사번'];
  const secondaryColumn = headerMap['보조룸메이드사번'];
  const qmColumn = headerMap['QM사번'];
  if (!roomColumn || !cleaningStatusColumn || !assignmentTypeColumn || !primaryColumn || !secondaryColumn || !qmColumn) {
    throw new Error('초기화 재업로드 배정 검증에 필요한 현재객실현황 열을 확인하세요.');
  }

  (newRows || []).forEach(row => {
    const roomNo = normalizeRoomNo_(row[roomColumn - 1]);
    if (!roomNo) return;
    const expected = expectedByRoom[roomNo] || null;
    const actualPrimary = String(row[primaryColumn - 1] || '').trim();
    const actualSecondary = String(row[secondaryColumn - 1] || '').trim();
    const actualQm = String(row[qmColumn - 1] || '').trim();
    const actualAssignmentType = String(row[assignmentTypeColumn - 1] || '').trim().toUpperCase();
    const actualCleaningStatus = String(row[cleaningStatusColumn - 1] || '').trim().toUpperCase();

    if (!expected) {
      if (actualPrimary || actualSecondary || actualQm || actualAssignmentType) {
        throw new Error(`${roomNo}호 초기화 재업로드에서 이전 배정정보가 남아 반영을 중단했습니다.`);
      }
      return;
    }

    if (actualPrimary !== expected.primaryEmployeeNo
        || actualSecondary !== expected.secondaryEmployeeNo
        || actualAssignmentType !== expected.assignmentType
        || actualQm
        || actualCleaningStatus !== 'ASSIGNED') {
      throw new Error(`${roomNo}호 초기화 재업로드 배정정보가 이번 업로드 배정과 일치하지 않아 반영을 중단했습니다.`);
    }
  });
}

function createRoomMaintenanceResetSummary_() { // (객실업로드 정비초기화 결과 기본값)
  return {
    total: 0,
    roomStatusChange: 0,
    cleaning: 0,
    qm: 0,
    qmChecklist: 0,
    dailyClose: 0,
    preservedOrders: true
  };
}

function resetRoomMaintenanceHistoryForUpload_(businessDate, site, updatedAt) { // (초기화 후 반영 정비이력만 소프트삭제·오더 유지)
  const result = createRoomMaintenanceResetSummary_();
  const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  if (historySheet.getLastRow() < 2) return result;

  const headerMap = getHeaderMap_(historySheet);
  const typeColumn = headerMap['기록구분'];
  const dateColumn = headerMap['업무일자'];
  const siteColumn = headerMap['사업장'];
  const deletedColumn = headerMap['삭제여부'];
  const updatedColumn = headerMap['수정일시'];
  if (!typeColumn || !dateColumn || !siteColumn || !deletedColumn) {
    throw new Error('업무이력 시트의 기록구분·업무일자·사업장·삭제여부 열을 확인하세요.');
  }

  const resetTypes = new Map([
    [String(NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE || '').trim(), 'roomStatusChange'],
    [String(NOVA.RECORD_TYPES.CLEANING || '').trim(), 'cleaning'],
    [String(NOVA.RECORD_TYPES.QM || '').trim(), 'qm'],
    [String(NOVA.RECORD_TYPES.QM_CHECKLIST || '').trim(), 'qmChecklist'],
    [String(NOVA.RECORD_TYPES.DAILY_CLOSE || '').trim(), 'dailyClose']
  ].filter(item => item[0]));

  const rowCount = historySheet.getLastRow() - 1;
  const typeValues = historySheet.getRange(2, typeColumn, rowCount, 1).getDisplayValues();
  const dateValues = historySheet.getRange(2, dateColumn, rowCount, 1).getDisplayValues();
  const siteValues = historySheet.getRange(2, siteColumn, rowCount, 1).getDisplayValues();
  const deletedValues = historySheet.getRange(2, deletedColumn, rowCount, 1).getDisplayValues();
  const matchedRows = [];

  for (let index = 0; index < rowCount; index += 1) {
    if (String(dateValues[index][0] || '').trim() !== businessDate) continue;
    if (String(siteValues[index][0] || '').trim() !== site) continue;
    if (String(deletedValues[index][0] || 'N').trim().toUpperCase() === 'Y') continue;
    const recordType = String(typeValues[index][0] || '').trim();
    const summaryKey = resetTypes.get(recordType);
    if (!summaryKey) continue;
    matchedRows.push(index + 2);
    result[summaryKey] += 1;
    result.total += 1;
  }

  groupRoomUploadResetRows_(matchedRows).forEach(group => {
    historySheet.getRange(group.start, deletedColumn, group.count, 1)
      .setValues(Array.from({ length: group.count }, () => ['Y']));
    if (updatedColumn) {
      historySheet.getRange(group.start, updatedColumn, group.count, 1)
        .setValues(Array.from({ length: group.count }, () => [updatedAt]));
    }
  });
  return result;
}

function groupRoomUploadResetRows_(rowNumbers) { // (정비초기화 대상 연속행 묶음)
  const sorted = Array.from(new Set((rowNumbers || []).map(Number).filter(Number.isFinite))).sort((a, b) => a - b);
  const groups = [];
  sorted.forEach(rowNumber => {
    const last = groups[groups.length - 1];
    if (last && last.start + last.count === rowNumber) {
      last.count += 1;
    } else {
      groups.push({ start: rowNumber, count: 1 });
    }
  });
  return groups;
}

function parseRoomUploadBlob_(blob, extension, master) { // (파일 형식별 객실현황 분석)
  switch (extension) {
    case 'csv':
      return parseRoomStatusCsv_(blob, master);
    case 'xlsx':
      return parseRoomStatusWorkbook_(blob, master);
    case 'xls':
      throw new Error('구형 XLS 파일은 지원하지 않습니다. Excel에서 XLSX 형식으로 다시 저장한 뒤 업로드하세요.');
    case 'pdf':
      return parseRoomStatusPdf_(blob, master);
    default:
      throw new Error('지원 파일은 XLSX, CSV, PDF입니다.');
  }
}

function isZipSignature_(bytes) { // (XLSX ZIP 파일 시그니처 확인)
  if (!bytes || bytes.length < 4) return false;
  const b0 = Number(bytes[0]) & 0xff;
  const b1 = Number(bytes[1]) & 0xff;
  const b2 = Number(bytes[2]) & 0xff;
  const b3 = Number(bytes[3]) & 0xff;
  if (b0 !== 0x50 || b1 !== 0x4b) return false;
  return (b2 === 0x03 && b3 === 0x04)
    || (b2 === 0x05 && b3 === 0x06)
    || (b2 === 0x07 && b3 === 0x08);
}

function parseRoomStatusWorkbook_(blob, master) { // (XLSX 내부 XML 직접 분석: Drive 변환 미사용)
  const extension = getFileExtension_(blob.getName());
  if (extension !== 'xlsx') {
    throw new Error('구형 XLS 파일은 지원하지 않습니다. Excel에서 XLSX 형식으로 다시 저장한 뒤 업로드하세요.');
  }

  let entries;
  try {
    const bytes = blob.getBytes();
    if (!isZipSignature_(bytes)) {
      throw new Error('파일 내부가 ZIP 기반 XLSX 형식이 아닙니다. 확장자만 .xlsx로 변경한 파일인지 확인하세요.');
    }

    // XLSX는 ZIP 구조이지만 업로드 Blob의 MIME은 Excel 형식으로 전달됩니다.
    // Utilities.unzip()은 application/zip Blob만 허용하므로 동일 바이트로 ZIP Blob을 새로 만듭니다.
    const zipBlob = Utilities.newBlob(
      bytes,
      'application/zip',
      String(blob.getName() || 'room-status.xlsx').replace(/\.xlsx$/i, '') + '.zip'
    );
    entries = Utilities.unzip(zipBlob);
  } catch (error) {
    throw new Error(`XLSX 파일을 열지 못했습니다. 파일이 손상되었거나 실제 형식이 XLSX가 아닙니다: ${error.message}`);
  }

  const files = {};
  entries.forEach(entry => {
    const name = normalizeZipPath_(entry.getName());
    if (name) files[name] = entry;
  });

  const workbookXml = readZipText_(files, 'xl/workbook.xml', 'XLSX 통합문서 정보');
  const relationshipsXml = readZipText_(files, 'xl/_rels/workbook.xml.rels', 'XLSX 시트 연결정보');
  const sharedStrings = files['xl/sharedStrings.xml']
    ? parseXlsxSharedStrings_(files['xl/sharedStrings.xml'].getDataAsString('UTF-8'))
    : [];
  const relationships = parseXlsxRelationships_(relationshipsXml);
  const sheetDefinitions = parseXlsxSheetDefinitions_(workbookXml);
  const sheetFiles = {};

  sheetDefinitions.forEach(definition => {
    const target = relationships[definition.relationshipId];
    if (!target) return;
    const path = normalizeXlsxTargetPath_(target);
    const sheetBlob = files[path];
    if (sheetBlob) sheetFiles[normalizeUploadHeading_(definition.name)] = sheetBlob;
  });

  const occurrences = {};
  const unknownRooms = new Set();
  const headings = [];

  NOVA_ROOM_UPLOAD.STATUS_SHEETS.forEach(def => {
    const sheetBlob = sheetFiles[normalizeUploadHeading_(def.sheetName)];
    if (!sheetBlob) return;
    headings.push(def.sheetName);
    const values = parseXlsxWorksheetValues_(sheetBlob.getDataAsString('UTF-8'), sharedStrings);
    values.forEach(value => collectWorkbookRoomValue_(value, def.code, master, occurrences, unknownRooms));
  });

  const parsed = buildParsedUpload_(occurrences, Array.from(unknownRooms), headings, []);
  const assignmentSheetBlob = sheetFiles[normalizeUploadHeading_(NOVA_ROOM_UPLOAD.ROOMMAID_ASSIGNMENT_SHEET)];
  if (!assignmentSheetBlob) {
    parsed.roommaidAssignment = emptyRoommaidUploadAssignment_(false);
    return parsed;
  }

  try {
    parsed.roommaidAssignment = parseRoommaidAssignmentWorksheet_(
      assignmentSheetBlob.getDataAsString('UTF-8'),
      sharedStrings,
      master
    );
  } catch (error) {
    const assignment = emptyRoommaidUploadAssignment_(true);
    assignment.errors.push(`시트 분석 오류: ${error.message}`);
    parsed.roommaidAssignment = assignment;
  }
  return parsed;
}

function normalizeZipPath_(path) { // (XLSX ZIP 내부 경로 정리)
  return String(path || '').replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/\.\//g, '/');
}

function readZipText_(files, path, label) { // (XLSX 필수 XML 읽기)
  const blob = files[normalizeZipPath_(path)];
  if (!blob) throw new Error(`${label}를 찾지 못했습니다. 정상적인 XLSX 파일인지 확인하세요.`);
  return blob.getDataAsString('UTF-8');
}

function parseXlsxSheetDefinitions_(xml) { // (XLSX 시트명과 관계 ID 분석)
  const result = [];
  const regex = /<sheet\b([^>]*)\/?\s*>/gi;
  let match;
  while ((match = regex.exec(String(xml || ''))) !== null) {
    const attributes = match[1] || '';
    const name = readXmlAttribute_(attributes, 'name');
    const relationshipId = readXmlAttribute_(attributes, 'r:id');
    if (name && relationshipId) result.push({ name, relationshipId });
  }
  return result;
}

function parseXlsxRelationships_(xml) { // (XLSX 관계 ID와 시트 파일 경로 분석)
  const result = {};
  const regex = /<Relationship\b([^>]*)\/?\s*>/gi;
  let match;
  while ((match = regex.exec(String(xml || ''))) !== null) {
    const attributes = match[1] || '';
    const id = readXmlAttribute_(attributes, 'Id');
    const target = readXmlAttribute_(attributes, 'Target');
    if (id && target) result[id] = target;
  }
  return result;
}

function normalizeXlsxTargetPath_(target) { // (XLSX 관계 Target을 ZIP 경로로 변환)
  let path = normalizeZipPath_(target);
  if (path.startsWith('../')) path = path.replace(/^(\.\.\/)+/, '');
  if (path.startsWith('/')) path = path.slice(1);
  if (!path.startsWith('xl/')) path = `xl/${path}`;
  const parts = [];
  path.split('/').forEach(part => {
    if (!part || part === '.') return;
    if (part === '..') parts.pop();
    else parts.push(part);
  });
  return parts.join('/');
}

function parseXlsxSharedStrings_(xml) { // (XLSX 공유문자열 분석)
  const strings = [];
  const itemRegex = /<si\b[^>]*>([\s\S]*?)<\/si>/gi;
  let itemMatch;
  while ((itemMatch = itemRegex.exec(String(xml || ''))) !== null) {
    const parts = [];
    const textRegex = /<t\b[^>]*>([\s\S]*?)<\/t>/gi;
    let textMatch;
    while ((textMatch = textRegex.exec(itemMatch[1])) !== null) {
      parts.push(decodeXmlText_(textMatch[1]));
    }
    strings.push(parts.join(''));
  }
  return strings;
}

function parseXlsxWorksheetValues_(xml, sharedStrings) { // (XLSX 워크시트 셀 값 추출)
  const values = [];
  const cellRegex = /<c\b([^>]*)>([\s\S]*?)<\/c>/gi;
  let cellMatch;
  while ((cellMatch = cellRegex.exec(String(xml || ''))) !== null) {
    const attributes = cellMatch[1] || '';
    const body = cellMatch[2] || '';
    const type = readXmlAttribute_(attributes, 't');
    if (type === 'e') continue;

    let value = '';
    if (type === 'inlineStr') {
      const parts = [];
      const textRegex = /<t\b[^>]*>([\s\S]*?)<\/t>/gi;
      let textMatch;
      while ((textMatch = textRegex.exec(body)) !== null) parts.push(decodeXmlText_(textMatch[1]));
      value = parts.join('');
    } else {
      const valueMatch = body.match(/<v\b[^>]*>([\s\S]*?)<\/v>/i);
      if (!valueMatch) continue;
      const raw = decodeXmlText_(valueMatch[1]);
      value = type === 's' ? (sharedStrings[Number(raw)] || '') : raw;
    }

    if (String(value || '').trim()) values.push(value);
  }
  return values;
}

function parseXlsxWorksheetGrid_(xml, sharedStrings) { // (XLSX 워크시트 행·열 구조 유지 추출)
  const rows = [];
  const rowRegex = /<row\b([^>]*)>([\s\S]*?)<\/row>/gi;
  let rowMatch;
  while ((rowMatch = rowRegex.exec(String(xml || ''))) !== null) {
    const rowAttributes = rowMatch[1] || '';
    const rowBody = rowMatch[2] || '';
    const declaredRowNumber = Number(readXmlAttribute_(rowAttributes, 'r'));
    const values = [];
    let fallbackColumn = 0;
    const cellRegex = /<c\b([^>]*)>([\s\S]*?)<\/c>/gi;
    let cellMatch;
    while ((cellMatch = cellRegex.exec(rowBody)) !== null) {
      const attributes = cellMatch[1] || '';
      const body = cellMatch[2] || '';
      const reference = readXmlAttribute_(attributes, 'r');
      const columnIndex = xlsxColumnIndexFromReference_(reference, fallbackColumn);
      fallbackColumn = columnIndex + 1;
      values[columnIndex] = parseXlsxCellValue_(attributes, body, sharedStrings);
    }
    if (values.some(value => String(value == null ? '' : value).trim())) {
      rows.push({
        rowNumber: Number.isFinite(declaredRowNumber) && declaredRowNumber > 0 ? declaredRowNumber : rows.length + 1,
        values
      });
    }
  }
  return rows;
}

function parseXlsxCellValue_(attributes, body, sharedStrings) { // (XLSX 셀 단일값 복원)
  const type = readXmlAttribute_(attributes, 't');
  if (type === 'e') return '';
  if (type === 'inlineStr') {
    const parts = [];
    const textRegex = /<t\b[^>]*>([\s\S]*?)<\/t>/gi;
    let textMatch;
    while ((textMatch = textRegex.exec(body)) !== null) parts.push(decodeXmlText_(textMatch[1]));
    return parts.join('');
  }
  const valueMatch = String(body || '').match(/<v\b[^>]*>([\s\S]*?)<\/v>/i);
  if (!valueMatch) return '';
  const raw = decodeXmlText_(valueMatch[1]);
  return type === 's' ? (sharedStrings[Number(raw)] || '') : raw;
}

function xlsxColumnIndexFromReference_(reference, fallbackIndex) { // (A1 셀주소를 0기준 열번호로 변환)
  const match = String(reference || '').toUpperCase().match(/^([A-Z]+)/);
  if (!match) return Number(fallbackIndex || 0);
  let value = 0;
  for (let index = 0; index < match[1].length; index += 1) {
    value = value * 26 + (match[1].charCodeAt(index) - 64);
  }
  return Math.max(0, value - 1);
}

function parseRoommaidAssignmentWorksheet_(xml, sharedStrings, master) { // (A~C 직원·D열 이후 객실번호 배정 시트 분석)
  const result = emptyRoommaidUploadAssignment_(true);
  const rows = parseXlsxWorksheetGrid_(xml, sharedStrings);
  const roommaidIndex = buildActiveRoommaidNameIndex_();
  const conflictedRooms = new Set();

  rows.forEach(row => {
    const values = row.values || [];
    const rawPrimaryName = String(values[0] == null ? '' : values[0]).trim();
    const rawPairName = String(values[1] == null ? '' : values[1]).trim();
    const rawTrainingName = String(values[2] == null ? '' : values[2]).trim();
    const roomCellValues = values.slice(3).filter(value => String(value == null ? '' : value).trim());
    const roomTokens = [];
    const invalidCellValues = [];
    roomCellValues.forEach(value => {
      const parsedCell = extractRoommaidAssignmentRoomTokens_(value);
      roomTokens.push(...parsedCell.roomNos);
      invalidCellValues.push(...parsedCell.invalidValues);
    });

    const hasAnyName = Boolean(rawPrimaryName || rawPairName || rawTrainingName);
    if (!hasAnyName && !roomTokens.length && !invalidCellValues.length) return;
    if (isRoommaidAssignmentHeaderRow_(rawPrimaryName, rawPairName, rawTrainingName) && !roomTokens.length) return;
    invalidCellValues.forEach(value => result.errors.push(`${row.rowNumber}행 인식 불가 객실값: ${value}`));
    if (!roomTokens.length) {
      if (hasAnyName && !isRoommaidAssignmentHeaderRow_(rawPrimaryName, rawPairName, rawTrainingName)) {
        result.warnings.push(`${row.rowNumber}행 ${rawPrimaryName || rawPairName || rawTrainingName}: 배정 객실이 없습니다.`);
      }
      return;
    }

    result.requestedCount += roomTokens.length;
    if (!rawPrimaryName) {
      result.errors.push(`${row.rowNumber}행: A열 주담당 이름이 비어 있어 ${roomTokens.join(', ')} 배정을 제외했습니다.`);
      return;
    }
    const legacyRoomColumns = [rawPairName, rawTrainingName]
      .filter(value => /^\d{4}(?:호)?$/.test(String(value || '').trim()));
    if (legacyRoomColumns.length) {
      result.errors.push(`${row.rowNumber}행 ${rawPrimaryName}: 구형 배정 양식이 감지되었습니다. B·C열은 직원명 전용이며 객실번호는 D열부터 입력하세요.`);
      return;
    }
    if (rawPairName && rawTrainingName) {
      result.errors.push(`${row.rowNumber}행 ${rawPrimaryName}: B열과 C열을 동시에 사용할 수 없습니다. 2인1조 또는 교육배정 중 하나만 입력하세요.`);
      return;
    }

    const primaryResult = resolveRoommaidUploadUser_(rawPrimaryName, roommaidIndex, row.rowNumber, 'A열 주담당');
    if (!primaryResult.ok) {
      result.errors.push(primaryResult.error);
      return;
    }

    const assignmentType = rawTrainingName
      ? trainingAssignmentTypeCode_()
      : (rawPairName ? pairAssignmentTypeCode_() : soloAssignmentTypeCode_());
    const rawSecondaryName = rawTrainingName || rawPairName;
    let secondaryRoommaid = null;
    if (rawSecondaryName) {
      const secondaryResult = resolveRoommaidUploadUser_(
        rawSecondaryName,
        roommaidIndex,
        row.rowNumber,
        rawTrainingName ? 'C열 교육보조' : 'B열 보조'
      );
      if (!secondaryResult.ok) {
        result.errors.push(secondaryResult.error);
        return;
      }
      secondaryRoommaid = secondaryResult.user;
      if (secondaryRoommaid.employeeNo === primaryResult.user.employeeNo) {
        result.errors.push(`${row.rowNumber}행 ${rawPrimaryName}: 주담당과 보조담당은 서로 다른 룸메이드여야 합니다.`);
        return;
      }
    }

    const primaryRoommaid = primaryResult.user;
    const assignmentSignature = [
      assignmentType,
      primaryRoommaid.employeeNo,
      secondaryRoommaid ? secondaryRoommaid.employeeNo : ''
    ].join('|');

    roomTokens.forEach(roomNo => {
      if (!master.byRoomNo[roomNo]) {
        result.errors.push(`${row.rowNumber}행 ${rawPrimaryName}: 객실마스터에 없는 객실 ${roomNo}호를 제외했습니다.`);
        return;
      }
      if (conflictedRooms.has(roomNo)) return;
      const existing = result.byRoom[roomNo];
      const existingSignature = existing
        ? [existing.assignmentType, existing.primaryEmployeeNo, existing.secondaryEmployeeNo || ''].join('|')
        : '';
      if (existing && existingSignature === assignmentSignature) {
        result.warnings.push(`${roomNo}호가 같은 배정조에 중복 입력되어 1건으로 처리됩니다.`);
        return;
      }
      if (existing && existingSignature !== assignmentSignature) {
        delete result.byRoom[roomNo];
        conflictedRooms.add(roomNo);
        result.errors.push(`${roomNo}호가 서로 다른 배정조에 중복 입력되어 해당 객실 배정을 제외했습니다.`);
        return;
      }
      result.byRoom[roomNo] = {
        assignmentType,
        primaryEmployeeNo: primaryRoommaid.employeeNo,
        primaryName: primaryRoommaid.name,
        secondaryEmployeeNo: secondaryRoommaid ? secondaryRoommaid.employeeNo : '',
        secondaryName: secondaryRoommaid ? secondaryRoommaid.name : '',
        // 이전 캐시 구조 호환용 별칭
        employeeNo: primaryRoommaid.employeeNo,
        name: primaryRoommaid.name,
        sourceRow: row.rowNumber
      };
    });
  });

  result.validCount = Object.keys(result.byRoom).length;
  const employeeNos = new Set();
  Object.keys(result.byRoom).forEach(roomNo => {
    const item = result.byRoom[roomNo] || {};
    if (item.primaryEmployeeNo || item.employeeNo) employeeNos.add(String(item.primaryEmployeeNo || item.employeeNo));
    if (item.secondaryEmployeeNo) employeeNos.add(String(item.secondaryEmployeeNo));
  });
  result.employeeCount = employeeNos.size;
  return result;
}

function resolveRoommaidUploadUser_(rawName, roommaidIndex, rowNumber, columnLabel) { // (배정 시트 이름을 활성 룸메이드 1명으로 확정)
  const name = String(rawName || '').trim();
  const candidates = roommaidIndex[normalizeRoommaidUploadName_(name)] || [];
  if (!candidates.length) {
    return { ok: false, user: null, error: `${rowNumber}행 ${columnLabel} ${name}: 활성 ROOMMAID 사용자계정에서 이름을 찾지 못했습니다.` };
  }
  if (candidates.length > 1) {
    return { ok: false, user: null, error: `${rowNumber}행 ${columnLabel} ${name}: 같은 이름의 룸메이드가 ${candidates.length}명이라 배정을 제외했습니다.` };
  }
  return { ok: true, user: candidates[0], error: '' };
}

function isRoommaidAssignmentHeaderRow_(primary, pair, training) { // (A~C 배정 시트 제목행 판별)
  const values = [primary, pair, training].map(value => normalizeRoommaidUploadName_(value).toUpperCase());
  const headerTokens = new Set([
    '이름', '성명', '룸메이드', '룸메이드명', 'ROOMMAID', 'NAME',
    '주담당', '주담당룸메이드', 'PRIMARY',
    '보조', '보조담당', '2인1조', 'PAIR',
    '교육', '교육보조', '교육담당', 'PAIRTRAINING'
  ]);
  return values.some(value => value && headerTokens.has(value.replace(/[()_\-\s]/g, '')));
}

function extractRoommaidAssignmentRoomTokens_(value) { // (셀 안 쉼표 포함 객실번호 추출)
  const text = String(value == null ? '' : value).trim();
  if (!text) return { roomNos: [], invalidValues: [] };
  const roomNos = [];
  const invalidValues = [];
  const parts = text.split(/[,，;；\n\r]+/).map(part => part.trim()).filter(Boolean);
  parts.forEach(part => {
    const normalized = normalizeRoomNo_(part.replace(/호\s*$/i, '').trim());
    if (/^\d{4}$/.test(normalized)) {
      roomNos.push(normalized);
      return;
    }
    const matches = Array.from(part.matchAll(/(?<!\d)\d{4}(?!\d)/g)).map(match => match[0]);
    if (matches.length) roomNos.push(...matches.map(normalizeRoomNo_));
    else invalidValues.push(part);
  });
  return { roomNos, invalidValues };
}

function buildActiveRoommaidNameIndex_() { // (활성 룸메이드 이름별 사용자계정 인덱스)
  const userIndex = getUserIndex_();
  const activeUsers = Array.isArray(userIndex.active)
    ? userIndex.active
    : Object.keys(userIndex.byEmployeeNo || {}).map(employeeNo => userIndex.byEmployeeNo[employeeNo]);
  const result = {};
  activeUsers.forEach(user => {
    if (!user || String(user.role || '').trim().toUpperCase() !== 'ROOMMAID') return;
    const employeeNo = String(user.employeeNo || '').trim();
    const name = String(user.name || '').trim();
    const key = normalizeRoommaidUploadName_(name);
    if (!employeeNo || !key) return;
    if (!result[key]) result[key] = [];
    result[key].push(user);
  });
  return result;
}

function normalizeRoommaidUploadName_(value) { // (룸메이드 이름 비교용 정리)
  return String(value || '').replace(/^\uFEFF/, '').trim().replace(/\s+/g, '');
}

function isRoommaidAssignmentHeader_(value) { // (배정 시트 제목행 판별)
  const normalized = normalizeRoommaidUploadName_(value).toUpperCase();
  return ['이름', '성명', '룸메이드', '룸메이드명', 'ROOMMAID', 'NAME'].includes(normalized);
}

function emptyRoommaidUploadAssignment_(sheetFound) { // (배정 시트 공통 빈 분석결과)
  return {
    sheetFound: Boolean(sheetFound),
    byRoom: {},
    requestedCount: 0,
    validCount: 0,
    employeeCount: 0,
    errors: [],
    warnings: []
  };
}

function normalizeRoommaidUploadAssignment_(value) { // (캐시·파일형식별 배정 분석결과 정규화)
  const source = value && typeof value === 'object' ? value : {};
  return {
    sheetFound: Boolean(source.sheetFound),
    byRoom: source.byRoom && typeof source.byRoom === 'object' ? source.byRoom : {},
    requestedCount: Number(source.requestedCount || 0),
    validCount: Number(source.validCount || Object.keys(source.byRoom || {}).length || 0),
    employeeCount: Number(source.employeeCount || 0),
    errors: Array.isArray(source.errors) ? source.errors.map(text => String(text || '')).filter(Boolean) : [],
    warnings: Array.isArray(source.warnings) ? source.warnings.map(text => String(text || '')).filter(Boolean) : []
  };
}

function compactRoommaidAssignmentByRoom_(byRoom) { // (미리보기 캐시용 1인·2인1조 배정정보 보존)
  const result = {};
  Object.keys(byRoom || {}).forEach(roomNo => {
    const assignment = byRoom[roomNo] || {};
    const primaryEmployeeNo = String(assignment.primaryEmployeeNo || assignment.employeeNo || '').trim();
    const primaryName = String(assignment.primaryName || assignment.name || '').trim();
    const secondaryEmployeeNo = String(assignment.secondaryEmployeeNo || '').trim();
    const secondaryName = String(assignment.secondaryName || '').trim();
    const assignmentType = String(assignment.assignmentType || soloAssignmentTypeCode_()).trim().toUpperCase();
    if (!primaryEmployeeNo) return;
    result[roomNo] = {
      assignmentType,
      primaryEmployeeNo,
      primaryName,
      secondaryEmployeeNo,
      secondaryName,
      employeeNo: primaryEmployeeNo,
      name: primaryName
    };
  });
  return result;
}

function buildRoommaidAssignmentPreviewWarnings_(assignment) { // (배정 시트 결과를 기존 미리보기 경고에 연결)
  const data = normalizeRoommaidUploadAssignment_(assignment);
  if (!data.sheetFound) return [];
  const messages = [
    `${NOVA_ROOM_UPLOAD.ROOMMAID_ASSIGNMENT_SHEET} 시트: 요청 ${data.requestedCount}실 · 유효 ${data.validCount}실 · 룸메이드 ${data.employeeCount}명`
  ];
  if (data.errors.length) {
    messages.push(`배정 시트 오류 ${data.errors.length}건은 객실현황 업로드를 막지 않으며 해당 배정만 제외됩니다.`);
    data.errors.slice(0, 12).forEach(text => messages.push(`[배정 제외] ${text}`));
    if (data.errors.length > 12) messages.push(`[배정 제외] 그 외 ${data.errors.length - 12}건`);
  }
  data.warnings.slice(0, 12).forEach(text => messages.push(`[배정 참고] ${text}`));
  if (data.warnings.length > 12) messages.push(`[배정 참고] 그 외 ${data.warnings.length - 12}건`);
  return messages;
}

function readXmlAttribute_(attributes, name) { // (XML 속성값 읽기)
  const escaped = String(name || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = String(attributes || '').match(new RegExp(`(?:^|\\s)${escaped}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`, 'i'));
  return match ? decodeXmlText_(match[1] != null ? match[1] : match[2]) : '';
}

function decodeXmlText_(value) { // (XML 엔티티 복원)
  return String(value == null ? '' : value)
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, number) => String.fromCodePoint(parseInt(number, 10)))
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

function parseRoomStatusCsv_(blob, master) { // (CSV 객실번호·객실상태 분석)
  const text = blob.getDataAsString('UTF-8').replace(/^\uFEFF/, '');
  let rows = Utilities.parseCsv(text);
  if (rows.length === 1 && String(rows[0][0] || '').includes(';')) rows = Utilities.parseCsv(text, ';');
  if (!rows.length) throw new Error('CSV 파일이 비어 있습니다.');

  const headers = rows[0].map(normalizeUploadHeading_);
  const roomIndex = headers.indexOf(normalizeUploadHeading_('객실번호'));
  const statusIndex = headers.indexOf(normalizeUploadHeading_('객실상태'));
  if (roomIndex < 0 || statusIndex < 0) {
    throw new Error('CSV 첫 행에 객실번호, 객실상태 열이 필요합니다.');
  }

  const occurrences = {};
  const unknownRooms = new Set();
  const invalidStatuses = new Set();
  const headings = new Set();
  rows.slice(1).forEach(row => {
    const roomNo = normalizeRoomNo_(row[roomIndex]);
    const statusDef = uploadStatusDefinition_(row[statusIndex]);
    if (!roomNo && !String(row[statusIndex] || '').trim()) return;
    if (!statusDef) {
      if (String(row[statusIndex] || '').trim()) invalidStatuses.add(String(row[statusIndex]).trim());
      return;
    }
    headings.add(statusDef.sheetName);
    if (!master.byRoomNo[roomNo]) {
      if (looksLikeRoomNo_(roomNo)) unknownRooms.add(roomNo);
      return;
    }
    addUploadOccurrence_(occurrences, roomNo, statusDef.code);
  });

  return buildParsedUpload_(occurrences, Array.from(unknownRooms), NOVA_ROOM_UPLOAD.STATUS_SHEETS.map(def => def.sheetName), Array.from(invalidStatuses));
}

function parseRoomStatusPdf_(blob, master) { // (PDF 텍스트 변환 후 상태 구간 분석)
  const temporaryId = importBlobAsGoogleFile_(blob, 'application/vnd.google-apps.document');
  try {
    const text = readConvertedDocumentText_(temporaryId);
    if (!String(text || '').trim()) throw new Error('PDF에서 텍스트를 읽지 못했습니다. 스캔 PDF는 인식되지 않을 수 있습니다.');

    const definitions = NOVA_ROOM_UPLOAD.STATUS_SHEETS.slice()
      .sort((a, b) => b.sheetName.length - a.sheetName.length);
    const occurrences = {};
    const headings = new Set();
    let current = null;

    String(text).split(/\r?\n/).forEach(line => {
      const compact = normalizeUploadHeading_(line);
      const found = definitions.find(def => compact.startsWith(normalizeUploadHeading_(def.sheetName)));
      let roomText = line;
      if (found) {
        current = found;
        headings.add(found.sheetName);
        const headingIndex = compact.indexOf(normalizeUploadHeading_(found.sheetName));
        if (headingIndex === 0) roomText = String(line).slice(found.sheetName.length);
      }
      if (!current) return;
      extractRoomTokens_(roomText).forEach(roomNo => {
        if (master.byRoomNo[roomNo]) addUploadOccurrence_(occurrences, roomNo, current.code);
      });
    });

    return buildParsedUpload_(occurrences, [], Array.from(headings), [], [
      'PDF는 변환된 텍스트에서 객실마스터와 일치하는 객실번호만 수집합니다. 반영 전 건수를 반드시 확인하세요.'
    ]);
  } finally {
    trashTemporaryFile_(temporaryId);
  }
}

function validateRoomUpload_(parsed, master) { // (누락 시트·상태관계·미등록 객실 검증)
  const required = new Set(NOVA_ROOM_UPLOAD.STATUS_SHEETS.map(def => def.sheetName));
  (parsed.sourceHeadings || []).forEach(name => required.delete(name));
  const missingSheets = Array.from(required);
  const unknownRooms = Array.from(new Set(parsed.unknownRooms || [])).sort(compareRoomNoText_);
  const invalidStatuses = Array.from(new Set(parsed.invalidStatuses || []));
  const statusByRoom = {};
  const counts = { VACANT_CLEAN: 0 };
  const duplicateRooms = [];
  const resolvedOverlaps = [];

  Object.keys(parsed.occurrences).forEach(roomNo => {
    const resolution = resolveUploadStatusCombination_(parsed.occurrences[roomNo]);
    if (resolution.conflict) {
      duplicateRooms.push({
        roomNo,
        statuses: resolution.statuses.map(uploadStatusLabel_)
      });
      return;
    }

    statusByRoom[roomNo] = resolution.status;
    counts[resolution.status] = (counts[resolution.status] || 0) + 1;
    if (resolution.overlap) {
      resolvedOverlaps.push({
        roomNo,
        statuses: resolution.statuses.map(uploadStatusLabel_),
        resolvedStatus: uploadStatusLabel_(resolution.status)
      });
    }
  });

  const matchedRooms = Object.keys(statusByRoom).length;
  counts.VACANT_CLEAN = Math.max(0, master.rooms.length - matchedRooms);
  parsed.statusByRoom = statusByRoom;

  const warnings = (parsed.warnings || []).slice();
  if (invalidStatuses.length) warnings.push(`인식하지 못한 객실상태: ${invalidStatuses.join(', ')}`);
  if (resolvedOverlaps.length) {
    const examples = resolvedOverlaps.slice(0, 8)
      .map(item => `${item.roomNo}(${item.statuses.join('/')}→${item.resolvedStatus})`)
      .join(', ');
    const suffix = resolvedOverlaps.length > 8 ? ` 외 ${resolvedOverlaps.length - 8}실` : '';
    warnings.push(`정상 중첩 ${resolvedOverlaps.length}실은 우선순위에 따라 자동 반영됩니다: ${examples}${suffix}`);
  }

  const canApply = !missingSheets.length && !duplicateRooms.length && !unknownRooms.length && !invalidStatuses.length && matchedRooms > 0;
  return {
    canApply,
    missingSheets,
    duplicateRooms,
    unknownRooms,
    warnings,
    counts,
    matchedRooms,
    resolvedOverlapCount: resolvedOverlaps.length
  };
}

function resolveUploadStatusCombination_(statusCodes) { // (시트 간 정상 중첩을 최종 객실상태로 정리)
  const statuses = Array.from(new Set(statusCodes || []));
  const stockStatuses = statuses.filter(code => ['STOCK', 'STOCK_RC', 'STOCK_HU'].includes(code));
  const stayStatuses = statuses.filter(code => ['STAY', 'DUE_OUT', 'CHECKED_OUT', 'RECHECKIN'].includes(code));

  if (stockStatuses.length && stayStatuses.length) {
    return { conflict: true, statuses };
  }

  if (stockStatuses.length) {
    const specialStatuses = stockStatuses.filter(code => code !== 'STOCK');
    if (specialStatuses.length > 1) {
      return { conflict: true, statuses };
    }
    const status = specialStatuses[0] || 'STOCK';
    return { conflict: false, statuses, status, overlap: statuses.length > 1 };
  }

  if (stayStatuses.length) {
    const priority = ['RECHECKIN', 'CHECKED_OUT', 'DUE_OUT', 'STAY'];
    const status = priority.find(code => stayStatuses.includes(code));
    return { conflict: false, statuses, status, overlap: statuses.length > 1 };
  }

  return { conflict: true, statuses };
}

function getActiveRoomMasterForSite_(site) { // (사업장별 사용 객실마스터 조회)
  const sheet = getRequiredSheet_(NOVA.SHEETS.ROOMS);
  const headerMap = getHeaderMap_(sheet);
  const rooms = [];
  const seen = {};
  if (sheet.getLastRow() >= 2) {
    const values = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getDisplayValues();
    values.forEach((row, offset) => {
      const data = rowObjectFromValues_(row, headerMap);
      const roomNo = normalizeRoomNo_(data['객실번호']);
      const roomSite = String(data['사업장'] || '').trim();
      const use = String(data['사용여부'] || '').trim().toUpperCase();
      if (!roomNo || roomSite !== site || ['N', '미사용', '사용안함'].includes(use)) return;
      if (!/^\d{4}$/.test(roomNo)) throw new Error(`객실마스터 ${offset + 2}행 객실번호는 4자리 숫자로 입력하세요: ${roomNo}`);
      if (seen[roomNo]) throw new Error(`객실마스터에 객실번호가 중복되었습니다: ${roomNo}`);
      seen[roomNo] = true;
      rooms.push({
        roomNo,
        site: roomSite,
        building: normalizeRoomBuilding_(data['동'], roomNo),
        roomType: String(data['객실타입'] || '').trim(),
        maintenanceType: String(data['정비타입'] || '').trim().toUpperCase()
      });
    });
  }
  rooms.sort((a, b) => compareRoomNoText_(a.roomNo, b.roomNo));
  const byRoomNo = {};
  const prefixes = {};
  rooms.forEach(room => {
    byRoomNo[room.roomNo] = room;
    prefixes[room.roomNo.slice(0, 2)] = true;
  });
  const signature = Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, rooms.map(room => `${room.roomNo}|${room.site}|${room.building}|${room.roomType}|${room.maintenanceType}`).join('\n'))
  );
  return { rooms, byRoomNo, prefixes, signature };
}

function buildUploadDepartureConfirmedAssignment_(roomNo, previous, roomStatus, operation, resetExisting) { // (업로드 퇴실예정→퇴실 담당자 알림대상 생성)
  if (resetExisting === true) return null;
  const previousRoomStatus = String(previous && previous['객실상태'] || '').trim().toUpperCase();
  const nextRoomStatus = String(roomStatus || '').trim().toUpperCase();
  if (previousRoomStatus !== 'DUE_OUT' || nextRoomStatus !== 'CHECKED_OUT') return null;
  const state = operation || {};
  const employeeNos = Array.from(new Set([state.roommaidEmployeeNo, state.secondaryRoommaidEmployeeNo]
    .map(value => String(value || '').trim()).filter(Boolean)));
  if (!employeeNos.length) return null;
  return {
    roomNo: String(roomNo || '').trim(),
    employeeNos,
    cleaningType: String(state.cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
    preassigned: normalizeYesNo_(previous && previous['선배정여부']) === 'Y',
    vip: normalizeYesNo_(previous && previous['VIP여부']) === 'Y',
    importantRoom: normalizeYesNo_(previous && previous['중요객실여부']) === 'Y'
  };
}

function resolveEffectiveUploadRoomStatus_(uploadedRoomStatus, previous) { // (업로드보다 당일 운영변경 우선 적용)
  const uploaded = String(uploadedRoomStatus || '').trim().toUpperCase();
  const previousRoomStatus = String(previous['객실상태'] || '').trim().toUpperCase();
  const previousCleaningStatus = String(previous['청소상태'] || '').trim().toUpperCase();

  if (uploaded === 'DUE_OUT' && ['CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU', 'RECHECKIN'].includes(previousRoomStatus)) {
    return previousRoomStatus;
  }
  if (isNovaRoomCleaningTargetStatus_(uploaded)
      && previousRoomStatus === 'VACANT_CLEAN'
      && isCleaningCompletedStatus_(previousCleaningStatus)) {
    return 'VACANT_CLEAN';
  }
  return uploaded;
}

function resolveUploadOperationState_(roomStatus, previous) { // (업로드 후 청소 진행상태 결정)
  if (['VACANT_CLEAN', 'RECHECKIN'].includes(roomStatus)) {
    return { cleaningStatus: 'COMPLETED', cleaningType: '', assignmentType: '', roommaidEmployeeNo: '', secondaryRoommaidEmployeeNo: '', qmEmployeeNo: '' };
  }
  const previousStatus = String(previous['청소상태'] || '').trim();
  const previousRoomStatus = String(previous['객실상태'] || '').trim();
  const previousRoommaidEmployeeNo = String(previous['룸메이드사번'] || '').trim();
  const activeStatuses = new Set(['ASSIGNED', 'CLEANING', 'QM_WAITING', 'QM_CHECKING', 'REWORK']);

  if (roomStatus === 'CHECKED_OUT' && previousRoomStatus === 'DUE_OUT') {
    return {
      cleaningStatus: 'WAITING',
      cleaningType: String(previous['정비유형'] || '').trim(),
      assignmentType: String(previous['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim(),
      roommaidEmployeeNo: previousRoommaidEmployeeNo,
      secondaryRoommaidEmployeeNo: String(previous['보조룸메이드사번'] || '').trim(),
      qmEmployeeNo: String(previous['QM사번'] || '').trim()
    };
  }

  const shouldPreserve = activeStatuses.has(previousStatus)
    || (previousStatus === 'WAITING' && previousRoomStatus === roomStatus && Boolean(previousRoommaidEmployeeNo))
    || (previousStatus === 'COMPLETED' && previousRoomStatus === roomStatus);
  if (shouldPreserve) {
    return {
      cleaningStatus: previousStatus,
      cleaningType: String(previous['정비유형'] || '').trim(),
      assignmentType: String(previous['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim(),
      roommaidEmployeeNo: String(previous['룸메이드사번'] || '').trim(),
      secondaryRoommaidEmployeeNo: String(previous['보조룸메이드사번'] || '').trim(),
      qmEmployeeNo: String(previous['QM사번'] || '').trim()
    };
  }
  if (['STAY', 'DUE_OUT'].includes(roomStatus)) {
    return { cleaningStatus: 'NOT_REQUIRED', cleaningType: '', assignmentType: '', roommaidEmployeeNo: '', secondaryRoommaidEmployeeNo: '', qmEmployeeNo: '' };
  }
  return { cleaningStatus: 'WAITING', cleaningType: '', assignmentType: '', roommaidEmployeeNo: '', secondaryRoommaidEmployeeNo: '', qmEmployeeNo: '' };
}


function enforceUploadRoomOperationState_(roomStatus, operation) { // (업로드 최종 청소상태 강제정합)
  const normalizedRoomStatus = String(roomStatus || '').trim().toUpperCase();
  if (['VACANT_CLEAN', 'RECHECKIN'].includes(normalizedRoomStatus)) {
    return {
      cleaningStatus: 'COMPLETED',
      cleaningType: '',
      assignmentType: '',
      roommaidEmployeeNo: '',
      secondaryRoommaidEmployeeNo: '',
      qmEmployeeNo: ''
    };
  }
  return operation || {
    cleaningStatus: 'WAITING',
    cleaningType: '',
    assignmentType: '',
    roommaidEmployeeNo: '',
    secondaryRoommaidEmployeeNo: '',
    qmEmployeeNo: ''
  };
}

function resolveUploadedRoommaidAssignment_(roomNo, roomStatus, previous, baseOperation, requested, usersByEmployeeNo) { // (업로드 1인·2인1조 배정 적용·기존 진행상태 보호)
  if (!requested) return { operation: baseOperation, applied: false, skipped: null };
  const assignmentType = String(requested.assignmentType || soloAssignmentTypeCode_()).trim().toUpperCase();
  const allowedTypes = new Set([soloAssignmentTypeCode_(), pairAssignmentTypeCode_(), trainingAssignmentTypeCode_()]);
  const primaryEmployeeNo = String(requested.primaryEmployeeNo || requested.employeeNo || '').trim();
  const primaryName = String(requested.primaryName || requested.name || '').trim();
  const secondaryEmployeeNo = String(requested.secondaryEmployeeNo || '').trim();
  const secondaryName = String(requested.secondaryName || '').trim();
  const skippedBase = {
    roomNo,
    employeeNo: primaryEmployeeNo,
    name: primaryName,
    primaryEmployeeNo,
    primaryName,
    secondaryEmployeeNo,
    secondaryName,
    assignmentType
  };

  const protectedReason = uploadAssignmentProtectedReason_(previous);
  if (protectedReason) {
    return { operation: baseOperation, applied: false, skipped: Object.assign({}, skippedBase, { reason: protectedReason }) };
  }

  const normalizedRoomStatus = String(roomStatus || '').trim().toUpperCase();
  if (['VACANT_CLEAN', 'RECHECKIN'].includes(normalizedRoomStatus)) {
    return { operation: baseOperation, applied: false, skipped: Object.assign({}, skippedBase, { reason: '공실청소완료·재입실 객실' }) };
  }
  if (!allowedTypes.has(assignmentType)) {
    return { operation: baseOperation, applied: false, skipped: Object.assign({}, skippedBase, { reason: '사용할 수 없는 배정유형' }) };
  }

  const primaryUser = usersByEmployeeNo && usersByEmployeeNo[primaryEmployeeNo];
  if (!primaryUser || primaryUser.enabled === false || String(primaryUser.role || '').trim().toUpperCase() !== 'ROOMMAID') {
    return { operation: baseOperation, applied: false, skipped: Object.assign({}, skippedBase, { reason: '최종 반영 시 활성 주담당 ROOMMAID 사용자계정 확인 불가' }) };
  }
  if (primaryName && normalizeRoommaidUploadName_(primaryName) !== normalizeRoommaidUploadName_(primaryUser.name)) {
    return { operation: baseOperation, applied: false, skipped: Object.assign({}, skippedBase, { reason: `배정 시트 주담당 이름(${primaryName})과 사용자계정 이름(${primaryUser.name}) 불일치` }) };
  }

  const pairAssignment = assignmentType === pairAssignmentTypeCode_() || assignmentType === trainingAssignmentTypeCode_();
  let secondaryUser = null;
  if (pairAssignment) {
    secondaryUser = usersByEmployeeNo && usersByEmployeeNo[secondaryEmployeeNo];
    if (!secondaryUser || secondaryUser.enabled === false || String(secondaryUser.role || '').trim().toUpperCase() !== 'ROOMMAID') {
      return { operation: baseOperation, applied: false, skipped: Object.assign({}, skippedBase, { reason: '최종 반영 시 활성 보조 ROOMMAID 사용자계정 확인 불가' }) };
    }
    if (secondaryName && normalizeRoommaidUploadName_(secondaryName) !== normalizeRoommaidUploadName_(secondaryUser.name)) {
      return { operation: baseOperation, applied: false, skipped: Object.assign({}, skippedBase, { reason: `배정 시트 보조 이름(${secondaryName})과 사용자계정 이름(${secondaryUser.name}) 불일치` }) };
    }
    if (secondaryUser.employeeNo === primaryUser.employeeNo) {
      return { operation: baseOperation, applied: false, skipped: Object.assign({}, skippedBase, { reason: '주담당과 보조담당이 동일함' }) };
    }
  } else if (secondaryEmployeeNo) {
    return { operation: baseOperation, applied: false, skipped: Object.assign({}, skippedBase, { reason: '1인 배정에 보조담당이 포함됨' }) };
  }

  const assignment = {
    roomNo,
    assignmentType,
    primaryEmployeeNo: primaryUser.employeeNo,
    primaryName: String(primaryUser.name || primaryName).trim(),
    secondaryEmployeeNo: secondaryUser ? secondaryUser.employeeNo : '',
    secondaryName: secondaryUser ? String(secondaryUser.name || secondaryName).trim() : '',
    employeeNo: primaryUser.employeeNo,
    name: String(primaryUser.name || primaryName).trim(),
    roomStatus: normalizedRoomStatus
  };
  return {
    operation: {
      cleaningStatus: 'ASSIGNED',
      cleaningType: normalCleaningTypeCode_(),
      assignmentType,
      roommaidEmployeeNo: primaryUser.employeeNo,
      secondaryRoommaidEmployeeNo: secondaryUser ? secondaryUser.employeeNo : '',
      qmEmployeeNo: ''
    },
    applied: true,
    assignment,
    skipped: null
  };
}

function uploadAssignmentProtectedReason_(previous) { // (기존 배정·청소·완료·QM 진행 보호 판정)
  const data = previous || {};
  const cleaningStatus = String(data['청소상태'] || '').trim().toUpperCase();
  const protectedStatuses = new Set([
    'ASSIGNED', 'CLEANING', 'COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'REWORK',
    'QM_COMPLETED', 'FINAL_COMPLETED', 'DONE'
  ]);
  if (protectedStatuses.has(cleaningStatus)) return `기존 ${cleaningStatus} 상태`;
  if (String(data['룸메이드사번'] || '').trim() || String(data['보조룸메이드사번'] || '').trim()) return '기존 룸메이드 배정 존재';
  if (String(data['QM사번'] || '').trim()) return '기존 QM 진행 정보 존재';
  return '';
}

function normalCleaningTypeCode_() { // (일반정비 코드)
  return String(NOVA.CLEANING_TYPES && NOVA.CLEANING_TYPES.NORMAL || 'NORMAL').trim().toUpperCase();
}

function soloAssignmentTypeCode_() { // (1인 배정 코드)
  return String(NOVA.ROOMMAID_ASSIGNMENT_TYPES && NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO || 'SOLO').trim().toUpperCase();
}

function pairAssignmentTypeCode_() { // (2인1조 배정 코드)
  return String(NOVA.ROOMMAID_ASSIGNMENT_TYPES && NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR || 'PAIR').trim().toUpperCase();
}

function trainingAssignmentTypeCode_() { // (2인1조 교육배정 코드)
  return String(NOVA.ROOMMAID_ASSIGNMENT_TYPES && NOVA.ROOMMAID_ASSIGNMENT_TYPES.PAIR_TRAINING || 'PAIR_TRAINING').trim().toUpperCase();
}

function appendRoomUploadAssignmentHistory_(assignments, context) { // (업로드 신규 1인·2인1조 배정 업무이력 일괄 기록)
  const items = Array.isArray(assignments) ? assignments : [];
  if (!items.length) return 0;
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const rows = items.map(item => {
    const assignmentType = String(item.assignmentType || soloAssignmentTypeCode_()).trim().toUpperCase();
    const primaryEmployeeNo = String(item.primaryEmployeeNo || item.employeeNo || '').trim();
    const secondaryEmployeeNo = String(item.secondaryEmployeeNo || '').trim();
    return createRowByHeaders_(sheet, {
      '기록ID': `CLEANING-${Utilities.getUuid()}`,
      '기록구분': NOVA.RECORD_TYPES.CLEANING,
      '업무일자': context.businessDate,
      '사업장': context.site,
      '객실번호': item.roomNo,
      '대상사번': primaryEmployeeNo,
      '처리상태': 'UPLOAD_ASSIGN_ROOMMAID',
      '세부내용JSON': JSON.stringify({
        action: 'UPLOAD_ASSIGN_ROOMMAID',
        sourceSheet: NOVA_ROOM_UPLOAD.ROOMMAID_ASSIGNMENT_SHEET,
        sourceFile: context.fileName,
        roomStatus: item.roomStatus,
        cleaningStatus: 'ASSIGNED',
        cleaningType: normalCleaningTypeCode_(),
        assignmentType,
        primaryEmployeeNo,
        secondaryEmployeeNo,
        primaryName: String(item.primaryName || item.name || '').trim(),
        secondaryName: String(item.secondaryName || '').trim(),
        creditUnit: 1
      }),
      '등록사번': context.registeredBy,
      '등록일시': context.registeredAt,
      '수정일시': context.registeredAt,
      '변경버전': context.version,
      '삭제여부': 'N'
    });
  });
  const startRow = sheet.getLastRow() + 1;
  ensureSheetRowCapacity_(sheet, startRow + rows.length - 1);
  sheet.getRange(startRow, 1, rows.length, rows[0].length).setValues(rows);
  return rows.length;
}

function queueRoomUploadAssignmentTelegrams_(assignments, context) { // (배정조별 주담당·보조 텔레그램 요약 연결)
  const warnings = [];
  const grouped = {};
  (assignments || []).forEach(item => {
    const assignmentType = String(item.assignmentType || soloAssignmentTypeCode_()).trim().toUpperCase();
    const primaryEmployeeNo = String(item.primaryEmployeeNo || item.employeeNo || '').trim();
    const secondaryEmployeeNo = String(item.secondaryEmployeeNo || '').trim();
    if (!primaryEmployeeNo) return;
    const key = [assignmentType, primaryEmployeeNo, secondaryEmployeeNo].join('|');
    if (!grouped[key]) grouped[key] = { assignmentType, primaryEmployeeNo, secondaryEmployeeNo, roomNos: [] };
    grouped[key].roomNos.push(String(item.roomNo || '').trim());
  });

  if (!Object.keys(grouped).length) return warnings;
  if (typeof queueRoommaidBulkAssignmentTelegram_ !== 'function') {
    warnings.push('queueRoommaidBulkAssignmentTelegram_ 함수가 없어 텔레그램 요약을 발송하지 못했습니다. 객실현황과 배정은 정상 반영되었습니다.');
    return warnings;
  }

  Object.keys(grouped).forEach(key => {
    const group = grouped[key];
    const primaryUser = context.usersByEmployeeNo && context.usersByEmployeeNo[group.primaryEmployeeNo];
    const secondaryUser = group.secondaryEmployeeNo
      ? context.usersByEmployeeNo && context.usersByEmployeeNo[group.secondaryEmployeeNo]
      : null;
    if (!primaryUser) {
      warnings.push(`${group.primaryEmployeeNo}: 텔레그램 주담당 사용자계정을 찾지 못했습니다.`);
      return;
    }
    if (group.secondaryEmployeeNo && !secondaryUser) {
      warnings.push(`${group.secondaryEmployeeNo}: 텔레그램 보조담당 사용자계정을 찾지 못했습니다.`);
    }
    const roomNos = Array.from(new Set(group.roomNos)).sort(compareRoomNoText_);
    try {
      queueRoommaidBulkAssignmentTelegram_({
        businessDate: context.businessDate,
        site: context.site,
        roomNos,
        cleaningType: normalCleaningTypeCode_(),
        assignmentType: group.assignmentType,
        primaryUser,
        secondaryUser,
        registeredBy: context.registeredBy,
        version: context.version
      });
    } catch (error) {
      warnings.push(`${String(primaryUser.name || group.primaryEmployeeNo).trim()} 배정조 텔레그램 요약 실패: ${error.message}`);
    }
  });
  return warnings;
}

function queueRoomUploadDepartureConfirmedTelegrams_(items, context) { // (객실업로드 퇴실확정 텔레그램 요약 연결)
  const targets = Array.isArray(items) ? items : [];
  if (!targets.length) return [];
  if (typeof queueRoommaidDepartureStatusBulkTelegrams_ !== 'function') {
    return ['queueRoommaidDepartureStatusBulkTelegrams_ 함수가 없어 퇴실변경 알림을 발송하지 못했습니다. 객실현황은 정상 반영되었습니다.'];
  }
  try {
    const result = queueRoommaidDepartureStatusBulkTelegrams_(targets, context || {});
    return Array.isArray(result && result.warnings) ? result.warnings : [];
  } catch (error) {
    return [`퇴실예정 → 퇴실 텔레그램 알림 등록 실패: ${error.message}`];
  }
}

function buildAppliedAssignmentSummary_(assignments) { // (업로드 이력용 주담당·보조별 객실 요약)
  const grouped = {};
  const add = (employeeNo, name, roomNo, role, assignmentType) => {
    const no = String(employeeNo || '').trim();
    if (!no) return;
    if (!grouped[no]) grouped[no] = { employeeNo: no, name: name || '', roomNos: [], primaryRoomNos: [], secondaryRoomNos: [], assignmentTypes: [] };
    grouped[no].roomNos.push(roomNo);
    (role === 'PRIMARY' ? grouped[no].primaryRoomNos : grouped[no].secondaryRoomNos).push(roomNo);
    grouped[no].assignmentTypes.push(assignmentType);
  };
  (assignments || []).forEach(item => {
    const assignmentType = String(item.assignmentType || soloAssignmentTypeCode_()).trim().toUpperCase();
    add(item.primaryEmployeeNo || item.employeeNo, item.primaryName || item.name, item.roomNo, 'PRIMARY', assignmentType);
    add(item.secondaryEmployeeNo, item.secondaryName, item.roomNo, 'SECONDARY', assignmentType);
  });
  return Object.keys(grouped).sort().map(employeeNo => ({
    employeeNo,
    name: grouped[employeeNo].name,
    roomNos: Array.from(new Set(grouped[employeeNo].roomNos)).sort(compareRoomNoText_),
    primaryRoomNos: Array.from(new Set(grouped[employeeNo].primaryRoomNos)).sort(compareRoomNoText_),
    secondaryRoomNos: Array.from(new Set(grouped[employeeNo].secondaryRoomNos)).sort(compareRoomNoText_),
    assignmentTypes: Array.from(new Set(grouped[employeeNo].assignmentTypes)).sort()
  }));
}

function buildRoomStatusUploadApplyMessage_(preview, roomCount, appliedCount, skippedCount, resetExisting, removedTargetRowCount, maintenanceReset) { // (객실현황·배정 최종 반영 안내)
  let message = resetExisting
    ? `${preview.site} ${preview.businessDate} 기존 객실현황 ${Number(removedTargetRowCount || 0)}행을 초기화하고 ${roomCount}실을 새로 반영했습니다.`
    : `${preview.site} ${preview.businessDate} 객실현황 ${roomCount}실을 반영했습니다.`;
  if (resetExisting) {
    const resetCount = Number(maintenanceReset && maintenanceReset.total || 0);
    message += ` 룸메이드·QM 정비현황 ${resetCount}건을 초기화했습니다. 하우스맨 오더는 유지됩니다.`;
  }
  if (preview.roommaidAssignment && preview.roommaidAssignment.sheetFound) {
    message += ` 룸메이드 신규 배정 ${appliedCount}실을 반영했습니다.`;
    if (skippedCount) message += resetExisting
      ? ` 유효하지 않거나 적용할 수 없는 ${skippedCount}실은 제외했습니다.`
      : ` 기존 진행상태 보호 등으로 ${skippedCount}실은 배정을 변경하지 않았습니다.`;
  }
  return message;
}

function repairRecheckinCleaningStatus_() { // (기존 재입실 대기 오류 일괄복구)
  const sheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
  if (sheet.getLastRow() < 2) return 0;

  const headerMap = getHeaderMap_(sheet);
  const requiredHeaders = [
    '객실상태', '청소상태', '정비유형', '배정유형',
    '룸메이드사번', '보조룸메이드사번', 'QM사번',
    '마지막변경버전', '수정일시'
  ];
  requiredHeaders.forEach(header => {
    if (!headerMap[header]) throw new Error(`현재객실현황 시트에 ${header} 열이 없습니다.`);
  });

  const rowCount = sheet.getLastRow() - 1;
  const columnCount = sheet.getLastColumn();
  const values = sheet.getRange(2, 1, rowCount, columnCount).getValues();
  const targetIndexes = [];

  values.forEach((row, index) => {
    const roomStatus = String(row[headerMap['객실상태'] - 1] || '').trim().toUpperCase();
    const cleaningStatus = String(row[headerMap['청소상태'] - 1] || '').trim().toUpperCase();
    const hasAssignment = [
      '정비유형', '배정유형', '룸메이드사번', '보조룸메이드사번', 'QM사번'
    ].some(header => String(row[headerMap[header] - 1] || '').trim());
    if (roomStatus === 'RECHECKIN' && (cleaningStatus !== 'COMPLETED' || hasAssignment)) {
      targetIndexes.push(index);
    }
  });

  if (!targetIndexes.length) return 0;

  const version = bumpDataVersion_({ domains: ['ROOM'] });
  const updatedAt = nowText_();
  targetIndexes.forEach(index => {
    const row = values[index];
    row[headerMap['청소상태'] - 1] = 'COMPLETED';
    row[headerMap['정비유형'] - 1] = '';
    row[headerMap['배정유형'] - 1] = '';
    row[headerMap['룸메이드사번'] - 1] = '';
    row[headerMap['보조룸메이드사번'] - 1] = '';
    row[headerMap['QM사번'] - 1] = '';
    row[headerMap['마지막변경버전'] - 1] = version;
    row[headerMap['수정일시'] - 1] = updatedAt;
  });

  sheet.getRange(2, 1, rowCount, columnCount).setValues(values);
  return targetIndexes.length;
}

function collectWorkbookRoomValue_(value, statusCode, master, occurrences, unknownRooms) { // (엑셀 셀 객실번호 검증)
  const roomNo = normalizeRoomNo_(value);
  if (!roomNo) return;
  if (master.byRoomNo[roomNo]) {
    addUploadOccurrence_(occurrences, roomNo, statusCode);
  } else if (looksLikeRoomNoForMaster_(roomNo, master)) {
    unknownRooms.add(roomNo);
  }
}

function addUploadOccurrence_(occurrences, roomNo, statusCode) { // (객실 상태 출현 기록)
  if (!occurrences[roomNo]) occurrences[roomNo] = [];
  occurrences[roomNo].push(statusCode);
}

function buildParsedUpload_(occurrences, unknownRooms, sourceHeadings, invalidStatuses, warnings) { // (공통 분석 결과 생성)
  return {
    occurrences: occurrences || {},
    statusByRoom: {},
    unknownRooms: unknownRooms || [],
    sourceHeadings: sourceHeadings || [],
    invalidStatuses: invalidStatuses || [],
    warnings: warnings || []
  };
}

function uploadStatusDefinition_(value) { // (업로드 상태명 코드 변환)
  const normalized = normalizeUploadHeading_(value);
  const aliases = {
    '재고': 'STOCK', 'STOCK': 'STOCK',
    '재고RC': 'STOCK_RC', '재고R/C': 'STOCK_RC', 'STOCKRC': 'STOCK_RC',
    '재고HU': 'STOCK_HU', '재고H/U': 'STOCK_HU', 'STOCKHU': 'STOCK_HU',
    '투숙': 'STAY', 'STAY': 'STAY',
    '퇴실예정': 'DUE_OUT', 'DUEOUT': 'DUE_OUT',
    '퇴실': 'CHECKED_OUT', 'CHECKEDOUT': 'CHECKED_OUT',
    '재입실': 'RECHECKIN', 'RECHECKIN': 'RECHECKIN'
  };
  const code = aliases[normalized];
  return NOVA_ROOM_UPLOAD.STATUS_SHEETS.find(def => def.code === code) || null;
}

function uploadStatusLabel_(code) { // (업로드 상태 코드 표시명)
  const found = NOVA_ROOM_UPLOAD.STATUS_SHEETS.find(def => def.code === code);
  return found ? found.label : code;
}

function normalizeUploadHeading_(value) { // (시트명·헤더 비교용 정리)
  return String(value || '').replace(/^\uFEFF/, '').trim().replace(/[\s_-]+/g, '').toUpperCase();
}

function normalizeRoomNo_(value) { // (객실번호 문자열 정리)
  const text = String(value == null ? '' : value).trim();
  if (!text) return '';
  return text.endsWith('.0') && /^\d+\.0$/.test(text) ? text.slice(0, -2) : text;
}

function looksLikeRoomNo_(value) { // (미등록 객실번호 후보 판별)
  return /^\d{4}$/.test(String(value || '').trim());
}

function looksLikeRoomNoForMaster_(value, master) { // (객실마스터 구조와 유사한 미등록 번호 판별)
  const roomNo = String(value || '').trim();
  return /^\d{4}$/.test(roomNo) && Boolean(master && master.prefixes && master.prefixes[roomNo.slice(0, 2)]);
}

function extractRoomTokens_(text) { // (PDF 텍스트에서 객실번호 후보 추출)
  return Array.from(String(text || '').matchAll(/(?<!\d)\d{4}(?!\d)/g)).map(match => match[0]);
}

function compareRoomNoText_(a, b) { // (객실번호 오름차순)
  const aNumber = Number(String(a || '').replace(/\D/g, ''));
  const bNumber = Number(String(b || '').replace(/\D/g, ''));
  if (Number.isFinite(aNumber) && Number.isFinite(bNumber) && aNumber !== bNumber) return aNumber - bNumber;
  return String(a || '').localeCompare(String(b || ''), 'ko');
}

function getFileExtension_(fileName) { // (파일 확장자 조회)
  const match = String(fileName || '').toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : '';
}

function rowFromHeaderMap_(lastColumn, headerMap, valuesByHeader) { // (헤더맵 기준 고속 행 생성)
  const row = new Array(lastColumn).fill('');
  Object.keys(valuesByHeader).forEach(header => {
    const column = headerMap[header];
    if (column) row[column - 1] = valuesByHeader[header];
  });
  return row;
}

function saveRoomUploadPreview_(previewId, payload) { // (업로드 미리보기 캐시+시트 2중 안전 저장)
  const encoded = encodeRoomUploadPreview_(payload);
  const cache = CacheService.getScriptCache();
  const cacheKey = NOVA_ROOM_UPLOAD.CACHE_PREFIX + String(previewId || '');

  // 빠른 재조회는 기존 ScriptCache를 사용하되, 캐시 조기삭제에 대비해 숨김 시트에도 동일 데이터를 보관합니다.
  try {
    cache.put(cacheKey, encoded, NOVA_ROOM_UPLOAD.CACHE_SECONDS);
  } catch (error) {}

  try {
    saveRoomUploadPreviewStore_(previewId, payload, encoded);
  } catch (error) {
    try { cache.remove(cacheKey); } catch (ignore) {}
    throw new Error(`업로드 미리보기 안전 저장에 실패했습니다. 잠시 후 다시 시도하세요. (${error && error.message ? error.message : '임시저장 오류'})`);
  }
}

function loadRoomUploadPreview_(previewId) { // (업로드 미리보기 캐시 우선·숨김 시트 복구)
  const safePreviewId = String(previewId || '').trim();
  if (!safePreviewId) return null;

  const cache = CacheService.getScriptCache();
  const cacheKey = NOVA_ROOM_UPLOAD.CACHE_PREFIX + safePreviewId;
  const cached = cache.get(cacheKey);
  if (cached) {
    try { return decodeRoomUploadPreview_(cached); } catch (error) {}
  }

  // CacheService가 만료시간 전이라도 조기 삭제될 수 있으므로 숨김 시트의 안전본에서 복구합니다.
  const stored = loadRoomUploadPreviewStore_(safePreviewId);
  if (!stored) return null;
  try {
    const payload = decodeRoomUploadPreview_(stored);
    try { cache.put(cacheKey, stored, NOVA_ROOM_UPLOAD.CACHE_SECONDS); } catch (error) {}
    return payload;
  } catch (error) {
    removeRoomUploadPreview_(safePreviewId, false);
    return null;
  }
}

function encodeRoomUploadPreview_(payload) { // (업로드 미리보기 gzip+Base64 인코딩)
  const compressed = Utilities.gzip(Utilities.newBlob(JSON.stringify(payload), 'application/json')).getBytes();
  const encoded = Utilities.base64EncodeWebSafe(compressed);
  if (encoded.length > 95000) throw new Error('업로드 데이터가 너무 큽니다. 사업장별로 나누어 업로드하세요.');
  return encoded;
}

function decodeRoomUploadPreview_(encoded) { // (업로드 미리보기 gzip+Base64 복원)
  const bytes = Utilities.base64DecodeWebSafe(String(encoded || ''));
  // CacheService·시트에는 문자열만 저장되므로 gzip MIME을 다시 지정해 복원합니다.
  const gzipBlob = Utilities.newBlob(bytes, 'application/gzip', 'nova-room-upload-preview.gz');
  return JSON.parse(Utilities.ungzip(gzipBlob).getDataAsString('UTF-8'));
}

function roomUploadPreviewStoreHeaders_() { // (숨김 임시저장 시트 헤더)
  return ['미리보기ID', '사번', '생성시각MS', '만료시각MS', '조각번호', '압축데이터'];
}

function getRoomUploadPreviewStoreSheet_(createIfMissing) { // (숨김 임시저장 시트 조회·필요 시 생성)
  const spreadsheet = getSpreadsheet_();
  let sheet = spreadsheet.getSheetByName(NOVA_ROOM_UPLOAD.PREVIEW_STORE_SHEET);
  if (!sheet && createIfMissing) {
    sheet = spreadsheet.insertSheet(NOVA_ROOM_UPLOAD.PREVIEW_STORE_SHEET);
    const headers = roomUploadPreviewStoreHeaders_();
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
    try { sheet.hideSheet(); } catch (error) {}
  }
  return sheet || null;
}

function withRoomUploadPreviewStoreLock_(callback, scriptWriteLockHeld) { // (미리보기 임시저장 동시쓰기 보호)
  const documentLock = LockService.getDocumentLock();
  if (documentLock) {
    documentLock.waitLock(5000);
    try { return callback(); } finally { documentLock.releaseLock(); }
  }

  // 독립 실행형 프로젝트 등에서 DocumentLock을 사용할 수 없을 때만 ScriptLock을 사용합니다.
  // applyRoomStatusUpload가 이미 ScriptLock을 가진 상태에서는 중첩 잠금을 피합니다.
  if (scriptWriteLockHeld === true) return callback();
  const scriptLock = LockService.getScriptLock();
  scriptLock.waitLock(5000);
  try { return callback(); } finally { scriptLock.releaseLock(); }
}

function rewriteRoomUploadPreviewStore_(sheet, rows) { // (숨김 임시저장 시트 데이터 재작성)
  const headerCount = roomUploadPreviewStoreHeaders_().length;
  const lastRow = sheet.getLastRow();
  if (lastRow > 1) sheet.getRange(2, 1, lastRow - 1, headerCount).clearContent();
  if (!(rows || []).length) return;
  const requiredLastRow = 1 + rows.length;
  if (sheet.getMaxRows() < requiredLastRow) sheet.insertRowsAfter(sheet.getMaxRows(), requiredLastRow - sheet.getMaxRows());
  sheet.getRange(2, 1, rows.length, headerCount).setValues(rows);
}

function pruneRoomUploadPreviewStore_(sheet, removePreviewId) { // (만료·지정 미리보기 임시데이터 정리)
  if (!sheet || sheet.getLastRow() < 2) return [];
  const headerCount = roomUploadPreviewStoreHeaders_().length;
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, headerCount).getValues();
  const now = Date.now();
  const removeId = String(removePreviewId || '').trim();
  const kept = rows.filter(row => {
    const id = String(row[0] || '').trim();
    const expiresAt = Number(row[3] || 0);
    if (!id || !String(row[5] || '')) return false;
    if (removeId && id === removeId) return false;
    return expiresAt > now;
  });
  rewriteRoomUploadPreviewStore_(sheet, kept);
  return kept;
}

function saveRoomUploadPreviewStore_(previewId, payload, encoded) { // (숨김 시트 미리보기 안전본 저장)
  const safePreviewId = String(previewId || '').trim();
  if (!safePreviewId) throw new Error('미리보기ID가 없습니다.');
  const safeEncoded = String(encoded || '');
  if (!safeEncoded) throw new Error('저장할 미리보기 데이터가 없습니다.');

  return withRoomUploadPreviewStoreLock_(() => {
    const sheet = getRoomUploadPreviewStoreSheet_(true);
    const kept = pruneRoomUploadPreviewStore_(sheet, safePreviewId);
    const createdAt = Number(payload && payload.createdAt || Date.now());
    const expiresAt = Date.now() + Number(NOVA_ROOM_UPLOAD.PREVIEW_STORE_TTL_MS || 0);
    const chunkSize = Math.max(1000, Number(NOVA_ROOM_UPLOAD.PREVIEW_STORE_CHUNK_CHARS || 40000));
    const chunks = [];
    for (let start = 0; start < safeEncoded.length; start += chunkSize) chunks.push(safeEncoded.slice(start, start + chunkSize));
    chunks.forEach((chunk, index) => {
      kept.push([safePreviewId, String(payload && payload.employeeNo || ''), createdAt, expiresAt, index + 1, chunk]);
    });
    rewriteRoomUploadPreviewStore_(sheet, kept);
    return true;
  }, false);
}

function loadRoomUploadPreviewStore_(previewId) { // (숨김 시트 미리보기 안전본 조회)
  const safePreviewId = String(previewId || '').trim();
  if (!safePreviewId) return '';

  return withRoomUploadPreviewStoreLock_(() => {
    const sheet = getRoomUploadPreviewStoreSheet_(false);
    if (!sheet || sheet.getLastRow() < 2) return '';
    const headerCount = roomUploadPreviewStoreHeaders_().length;
    const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, headerCount).getValues();
    const now = Date.now();
    const matched = rows.filter(row => String(row[0] || '').trim() === safePreviewId);
    if (!matched.length) return '';
    if (matched.some(row => Number(row[3] || 0) <= now)) {
      pruneRoomUploadPreviewStore_(sheet, safePreviewId);
      return '';
    }
    matched.sort((a, b) => Number(a[4] || 0) - Number(b[4] || 0));
    for (let index = 0; index < matched.length; index += 1) {
      if (Number(matched[index][4] || 0) !== index + 1) {
        pruneRoomUploadPreviewStore_(sheet, safePreviewId);
        return '';
      }
    }
    return matched.map(row => String(row[5] || '')).join('');
  }, false);
}

function removeRoomUploadPreview_(previewId, scriptWriteLockHeld) { // (반영완료·손상 미리보기 캐시와 안전본 동시 삭제)
  const safePreviewId = String(previewId || '').trim();
  if (!safePreviewId) return;
  try { CacheService.getScriptCache().remove(NOVA_ROOM_UPLOAD.CACHE_PREFIX + safePreviewId); } catch (error) {}
  withRoomUploadPreviewStoreLock_(() => {
    const sheet = getRoomUploadPreviewStoreSheet_(false);
    if (sheet) pruneRoomUploadPreviewStore_(sheet, safePreviewId);
  }, scriptWriteLockHeld === true);
}

function importBlobAsGoogleFile_(blob, targetMimeType) { // (Drive REST API로 임시 변환 파일 생성: 고급 서비스 미사용)
  const sourceMimeType = resolveUploadMimeType_(blob);
  const bytes = blob.getBytes();
  const token = ScriptApp.getOAuthToken();
  const query = targetMimeType === 'application/vnd.google-apps.document' ? '&ocrLanguage=ko' : '';
  const initiateUrl = `https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,mimeType${query}`;
  const metadata = {
    name: `NOVA_TEMP_${Date.now()}_${blob.getName() || 'upload'}`,
    mimeType: targetMimeType
  };

  const initiateResponse = UrlFetchApp.fetch(initiateUrl, {
    method: 'post',
    contentType: 'application/json; charset=UTF-8',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Upload-Content-Type': sourceMimeType,
      'X-Upload-Content-Length': String(bytes.length)
    },
    payload: JSON.stringify(metadata),
    muteHttpExceptions: true
  });

  const initiateCode = initiateResponse.getResponseCode();
  if (initiateCode < 200 || initiateCode >= 300) {
    throwDriveConversionError_(initiateCode, initiateResponse.getContentText());
  }

  const location = getHttpHeaderIgnoreCase_(initiateResponse.getAllHeaders(), 'Location');
  if (!location) throw new Error('Drive 변환 업로드 주소를 받지 못했습니다.');

  const uploadResponse = UrlFetchApp.fetch(location, {
    method: 'put',
    contentType: sourceMimeType,
    headers: { Authorization: `Bearer ${token}` },
    payload: bytes,
    muteHttpExceptions: true
  });
  const uploadCode = uploadResponse.getResponseCode();
  if (uploadCode < 200 || uploadCode >= 300) {
    throwDriveConversionError_(uploadCode, uploadResponse.getContentText());
  }

  const result = JSON.parse(uploadResponse.getContentText() || '{}');
  if (!result.id) throw new Error('변환된 임시 파일 ID를 받지 못했습니다.');
  return result.id;
}

function throwDriveConversionError_(statusCode, responseText) { // (Drive 변환 오류 한글 안내)
  const text = String(responseText || '');
  if (statusCode === 401 || /invalid.*credential|unauthenticated/i.test(text)) {
    throw new Error('Google Drive 변환 권한이 만료되었거나 승인되지 않았습니다. authorizeNovaDriveConversion()을 한 번 실행하세요.');
  }
  if (statusCode === 403 && /accessNotConfigured|SERVICE_DISABLED|has not been used|disabled/i.test(text)) {
    throw new Error('연결된 Google Cloud 프로젝트에서 Google Drive API가 비활성화되어 있습니다. XLSX·CSV는 정상 업로드할 수 있으며, PDF 사용 시에만 Drive API 활성화가 필요합니다.');
  }
  if (statusCode === 403) {
    throw new Error(`Google Drive 변환 권한이 거부되었습니다. (${statusCode})`);
  }
  throw new Error(`파일 변환에 실패했습니다. (${statusCode}) ${text.slice(0, 300)}`);
}

function getHttpHeaderIgnoreCase_(headers, targetName) { // (HTTP 응답 헤더 대소문자 무시 조회)
  const target = String(targetName || '').toLowerCase();
  const source = headers || {};
  const key = Object.keys(source).find(name => String(name).toLowerCase() === target);
  return key ? String(source[key] || '') : '';
}

function authorizeNovaDriveConversion() { // (Drive REST 변환 권한 사전 승인: Drive 고급 서비스 미사용)
  const token = ScriptApp.getOAuthToken();
  if (!token) throw new Error('Google OAuth 토큰을 발급받지 못했습니다.');
  return {
    ok: true,
    message: 'Google Drive 변환 권한 확인이 완료되었습니다. XLSX 업로드는 이 권한 없이도 직접 분석됩니다.',
    checkedAt: nowText_()
  };
}

function resolveUploadMimeType_(blob) { // (확장자 기준 원본 MIME 유형 보정)
  const extension = getFileExtension_(blob.getName());
  const byExtension = {
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    xls: 'application/vnd.ms-excel',
    pdf: 'application/pdf',
    csv: 'text/csv'
  };
  return byExtension[extension] || blob.getContentType() || 'application/octet-stream';
}

function openConvertedSpreadsheet_(fileId) { // (변환된 엑셀 파일 열기 재시도)
  let lastError = null;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      return SpreadsheetApp.openById(fileId);
    } catch (error) {
      lastError = error;
      Utilities.sleep(300 * (attempt + 1));
    }
  }
  throw new Error(`엑셀 변환 파일을 열지 못했습니다: ${lastError ? lastError.message : '알 수 없는 오류'}`);
}

function readConvertedDocumentText_(fileId) { // (변환된 PDF 문서 텍스트 읽기 재시도)
  let lastError = null;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      return DocumentApp.openById(fileId).getBody().getText();
    } catch (error) {
      lastError = error;
      Utilities.sleep(400 * (attempt + 1));
    }
  }
  throw new Error(`PDF 변환 문서를 열지 못했습니다: ${lastError ? lastError.message : '알 수 없는 오류'}`);
}

function trashTemporaryFile_(fileId) { // (Drive REST API로 임시파일 휴지통 이동)
  if (!fileId) return;
  try {
    UrlFetchApp.fetch(`https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}?fields=id,trashed`, {
      method: 'patch',
      contentType: 'application/json; charset=UTF-8',
      headers: { Authorization: `Bearer ${ScriptApp.getOAuthToken()}` },
      payload: JSON.stringify({ trashed: true }),
      muteHttpExceptions: true
    });
  } catch (error) {
    console.warn(`임시파일 삭제 실패: ${fileId} ${error.message}`);
  }
}


function buildUploadRoomsByStatus_(statusByRoom) { // (마감일지용 최초 객실상태 압축 저장)
  const result = {};
  Object.keys(statusByRoom || {}).forEach(roomNo => {
    const normalizedRoomNo = normalizeRoomNo_(roomNo);
    const status = String(statusByRoom[roomNo] || 'VACANT_CLEAN').trim().toUpperCase();
    if (!normalizedRoomNo) return;
    if (!result[status]) result[status] = [];
    result[status].push(normalizedRoomNo);
  });
  Object.keys(result).forEach(status => result[status].sort(compareRoomNoText_));
  return result;
}
