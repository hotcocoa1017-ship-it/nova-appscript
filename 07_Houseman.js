/**
 * 하우스맨 오더 등록·처리현황
 */
function createHousemanOrder(token, payload) { // (하우스맨 오더 등록·고속 저장)
  return measureResponse_('createHousemanOrder', () => {
    const startedMs = Date.now();
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = normalizeHousemanPayload_(payload);
    if (!safe.roomNo) throw new Error('객실번호를 입력하세요.');
    if (!safe.site) throw new Error('사업장을 선택하세요.');
    if (!safe.part) throw new Error('파트를 선택하세요.');
    if (!safe.items.length) throw new Error('품목을 한 개 이상 입력하세요.');

    const lock = LockService.getScriptLock();
    const lockRequestedMs = Date.now();
    lock.waitLock(10000);
    const lockAcquiredMs = Date.now();
    let order;
    let version;
    let autoAssignment = null;
    let telegramDispatch = { queued: false, queueRecordId: '', queueRowNumber: 0, reminderScheduled: false };
    let autoAssignMs = 0;
    let writeMs = 0;
    let flushMs = 0;

    try {
      // Realtime 선저장 후 백그라운드 Sheet 미러가 재시도되어도 동일 오더를 중복 생성하지 않습니다.
      if (safe.realtimeOrderId) {
        const dedupSheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
        const existing = findHousemanOrderRow_(dedupSheet, safe.realtimeOrderId, 0);

        if (existing) {
          const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
          const statusCodeMap = {};

          getCodes_('하우스맨상태').forEach(code => {
            statusCodeMap[code.code] = code.label;
          });

          const existingOrder = housemanOrderObject_(
            existing.data,
            existing.rowNumber,
            usersByEmployeeNo,
            statusCodeMap
          );

          return {
            ok: true,
            version: existingOrder.version,
            order: existingOrder,
            autoAssignment: null,
            telegram: telegramDispatch,
            mirrorDuplicate: true,
            timing: {
              lockWaitMs: Math.max(0, lockAcquiredMs - lockRequestedMs),
              autoAssignMs: 0,
              writeMs: 0,
              flushMs: 0,
              coreMs: Math.max(0, Date.now() - lockAcquiredMs),
              totalMs: Math.max(0, Date.now() - startedMs)
            }
          };
        }
      }

      const autoAssignStartedMs = Date.now();

      if (safe.assignmentMode === 'AUTO') {
        // Realtime 등록 시 화면에서 이미 계산한 동일 담당동 후보를
        // Sheet 미러에도 그대로 사용합니다.
        // 일반 등록은 기존 자동배정 방식을 그대로 유지합니다.
        autoAssignment =
          safe.realtimeOrderId && safe.realtimeAssignmentSnapshot
            ? normalizeRealtimeHousemanAssignmentSnapshot_(
                safe.businessDate,
                safe.site,
                safe.roomNo,
                safe.realtimeAssignmentSnapshot
              )
            : resolveHousemanAutoAssignee_(
                safe.businessDate,
                safe.site,
                safe.roomNo
              );

        safe.assignedEmployeeNo = autoAssignment.employeeNo;

      } else if (safe.assignmentMode === 'UNASSIGNED') {
        safe.assignedEmployeeNo = '';

      } else if (safe.assignedEmployeeNo) {
        const assigned = getActiveUserByEmployeeNo_(safe.assignedEmployeeNo);

        if (!assigned || assigned.role !== 'HOUSEMAN') {
          throw new Error('사용 가능한 하우스맨 계정이 아닙니다.');
        }
      }

      autoAssignMs = Math.max(
        0,
        Date.now() - autoAssignStartedMs
      );

      version = reserveDataVersion_({
        lockHeld: true
      });

      const orderId =
        safe.realtimeOrderId ||
        `HO-${safe.businessDate.replaceAll('-', '')}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`;

      const statusCode =
        safe.assignedEmployeeNo
          ? 'ASSIGNED'
          : 'REGISTERED';

      const now = nowText_();
      const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const headerMap = getHeaderMap_(sheet);
      const usersByEmployeeNo = getUserIndex_().byEmployeeNo;

      const statusCodeMap = {};

      getCodes_('하우스맨상태').forEach(code => {
        statusCodeMap[code.code] = code.label;
      });

      const itemSummary = safe.items
        .map(item =>
          item.quantity > 1
            ? `${item.name}×${item.quantity}`
            : item.name
        )
        .join(', ');

      const totalQuantity = safe.items.reduce(
        (sum, item) => sum + item.quantity,
        0
      );

      const detail = {
        items: safe.items,
        requester: safe.requester,
        requestSource: safe.requestSource,
        createdFrom: 'ORDER_DESKTOP',
        assignmentMode: safe.assignmentMode,
        autoAssigned: Boolean(autoAssignment),

        assignedBuilding: autoAssignment
          ? autoAssignment.building
          : normalizeRoomBuilding_('', safe.roomNo),

        assignedShiftCode: autoAssignment
          ? autoAssignment.currentShift
          : '',

        assignedShiftCodes: autoAssignment
          ? autoAssignment.activeShiftCodes
          : [],

        routeCandidateEmployeeNos: autoAssignment
          ? autoAssignment.employeeNos
          : (
              safe.assignedEmployeeNo
                ? [safe.assignedEmployeeNo]
                : []
            ),

        routeCandidateNames: autoAssignment
          ? autoAssignment.names
          : (
              safe.assignedEmployeeNo
                ? [
                    usersByEmployeeNo[safe.assignedEmployeeNo]?.name ||
                    safe.assignedEmployeeNo
                  ]
                : []
            ),

        routeLocked: !autoAssignment,

        handoverTargetShift: safe.handover
          ? resolveHandoverTargetShift_(now)
          : ''
      };

      const orderRow = createRowByHeaders_(sheet, {
        '기록ID': orderId,
        '기록구분': NOVA.RECORD_TYPES.HOUSEMAN_ORDER,
        '업무일자': safe.businessDate,
        '사업장': safe.site,
        '객실번호': safe.roomNo,
        '대상사번': safe.assignedEmployeeNo,
        '처리상태': statusCode,
        '세부내용JSON': JSON.stringify(detail),
        '등록사번': user.employeeNo,
        '등록일시': now,
        '수정일시': now,
        '파트': safe.part,
        '품목': itemSummary,
        '수량': totalQuantity,
        '추가내용': safe.note,
        '요청자': safe.requester,
        '배정사번': safe.assignedEmployeeNo,
        '중요여부': safe.important ? 'Y' : 'N',
        '인수인계여부': safe.handover ? 'Y' : 'N',
        '변경버전': version,
        '삭제여부': 'N'
      });

      const startRow = sheet.getLastRow() + 1;

      order = housemanOrderObject_(
        rowObjectFromValues_(orderRow, headerMap),
        startRow,
        usersByEmployeeNo,
        statusCodeMap
      );

      const auditRow = buildHousemanAuditRow_(
        sheet,
        order,
        'CREATED',
        user.employeeNo,
        version,
        {
          assignmentMode: safe.assignmentMode,
          autoAssignment: autoAssignment || null
        }
      );

      const telegramPrepared =
        prepareHousemanOrderFastTelegramRows_(
          sheet,
          order,
          'CREATED',
          {
            firstRowNumber: startRow + 2
          }
        );

      const rows = [
        orderRow,
        auditRow
      ].concat(
        telegramPrepared.rows || []
      );

      const writeStartedMs = Date.now();

      ensureSheetRowCapacity_(
        sheet,
        startRow + rows.length - 1
      );

      sheet
        .getRange(
          startRow,
          1,
          rows.length,
          orderRow.length
        )
        .setValues(rows);

      writeMs = Math.max(
        0,
        Date.now() - writeStartedMs
      );

      const flushStartedMs = Date.now();

      SpreadsheetApp.flush();

      flushMs = Math.max(
        0,
        Date.now() - flushStartedMs
      );

      publishDataVersion_(
        version,
        {
          domains: ['ORDER'],
          businessDate: safe.businessDate,
          site: safe.site,
          lockHeld: true
        }
      );

      telegramDispatch = {
        queued: Boolean(
          telegramPrepared.queueRecordId
        ),
        queueRecordId:
          telegramPrepared.queueRecordId || '',
        queueRowNumber:
          Number(
            telegramPrepared.queueRowNumber || 0
          ),
        reminderScheduled: Boolean(
          telegramPrepared.reminderRecordId
        ),
        reminderRecordId:
          telegramPrepared.reminderRecordId || ''
      };

    } finally {
      lock.releaseLock();
    }

    const finishedMs = Date.now();

    return {
      ok: true,
      version,
      order,
      autoAssignment,
      telegram: telegramDispatch,
      timing: {
        lockWaitMs: Math.max(
          0,
          lockAcquiredMs - lockRequestedMs
        ),
        autoAssignMs,
        writeMs,
        flushMs,
        coreMs: Math.max(
          0,
          finishedMs - lockAcquiredMs
        ),
        totalMs: Math.max(
          0,
          finishedMs - startedMs
        )
      }
    };
  });
}


function updateHousemanOrder(token, payload) { // (하우스맨 오더 상태·내용 수정)
  return measureResponse_('updateHousemanOrder', () => {
    const auth = verifyNovaToken(token);

    if (!auth.ok) {
      throw new Error('로그인이 필요합니다.');
    }

    const user = auth.user;

    const action = String(
      payload && payload.action || ''
    )
      .trim()
      .toUpperCase();

    const orderId = String(
      payload && payload.orderId || ''
    ).trim();

    if (!orderId) {
      throw new Error('오더 번호가 없습니다.');
    }

    const writeLock = LockService.getScriptLock();

    if (
      !writeLock.tryLock(
        Number(
          NOVA.WRITE_LOCK_TIMEOUT_MS || 2500
        )
      )
    ) {
      const busyError = new Error(
        '동시 오더 처리가 많습니다. 잠시 후 다시 처리하세요.'
      );

      busyError.code = 'BUSY_RETRY';

      throw busyError;
    }

    try {
      const sheet = getRequiredSheet_(
        NOVA.SHEETS.HISTORY
      );

      const found = findHousemanOrderRow_(
        sheet,
        orderId,
        payload && payload.rowNumber
      );

      if (!found) {
        throw new Error(
          '하우스맨 오더를 찾을 수 없습니다.'
        );
      }

      const usersByEmployeeNo =
        getUserIndex_().byEmployeeNo;

      const statusCodeMap = {};

      getCodes_('하우스맨상태').forEach(code => {
        statusCodeMap[code.code] = code.label;
      });

      const current = housemanOrderObject_(
        found.data,
        found.rowNumber,
        usersByEmployeeNo,
        statusCodeMap
      );

      assertExpectedVersion_(
        payload && payload.expectedVersion,
        current.version,
        `오더 ${orderId}`
      );

      let currentDetail = {};

      try {
        currentDetail = JSON.parse(
          String(
            found.data['세부내용JSON'] || '{}'
          )
        );
      } catch (error) {
        currentDetail = {};
      }

      const role = String(
        user.role || ''
      ).toUpperCase();

      const isManager =
        role === 'ADMIN' ||
        role === 'ORDER';

      const isAssignedHouseman =
        role === 'HOUSEMAN' &&
        current.assignedEmployeeNo ===
          user.employeeNo;

      const isRouteCandidate =
        role === 'HOUSEMAN' &&
        ['ACCEPT', 'ACCEPT_START']
          .includes(action) &&
        isHousemanOrderRouteCandidate_(
          current,
          user.employeeNo
        );

      if (
        !isManager &&
        !isAssignedHouseman &&
        !isRouteCandidate
      ) {
        throw new Error(
          '이 오더를 처리할 권한이 없습니다.'
        );
      }

      const now = nowText_();

      const updates = {
        '수정일시': now
      };

      let auditDetail = {};

      if (
        role === 'HOUSEMAN' &&
        current.statusCode === 'ASSIGNED' &&
        current.routeLocked !== true &&
        ![
          'ACCEPT',
          'ACCEPT_START'
        ].includes(action)
      ) {
        throw new Error(
          '공동 전달 오더는 먼저 접수한 후 처리할 수 있습니다.'
        );
      }

      switch (action) {

        case 'ASSIGN': {
          if (!isManager) {
            throw new Error(
              '직원배정은 오더테이커만 가능합니다.'
            );
          }

          const employeeNo = String(
            payload.employeeNo || ''
          ).trim();

          if (!employeeNo) {
            throw new Error(
              '배정 직원을 선택하세요.'
            );
          }

          const assigned =
            getActiveUserByEmployeeNo_(
              employeeNo
            );

          if (
            !assigned ||
            assigned.role !== 'HOUSEMAN'
          ) {
            throw new Error(
              '사용 가능한 하우스맨 계정이 아닙니다.'
            );
          }

          updates['배정사번'] = employeeNo;
          updates['대상사번'] = employeeNo;
          updates['처리상태'] = 'ASSIGNED';

          const assignDetail =
            Object.assign(
              {},
              currentDetail
            );

          assignDetail.assignmentMode =
            'MANUAL';

          assignDetail.autoAssigned =
            false;

          assignDetail.assignedBuilding =
            normalizeRoomBuilding_(
              '',
              current.roomNo
            );

          assignDetail.assignedShiftCode =
            '';

          assignDetail.assignedShiftCodes =
            [];

          assignDetail
            .routeCandidateEmployeeNos =
            [employeeNo];

          assignDetail.routeCandidateNames =
            [
              assigned.name ||
              employeeNo
            ];

          assignDetail.routeLocked =
            true;

          assignDetail
            .acceptedByEmployeeNo = '';

          assignDetail
            .releasedCandidateEmployeeNos =
            [];

          updates['세부내용JSON'] =
            JSON.stringify(assignDetail);

          auditDetail.employeeNo =
            employeeNo;

          auditDetail.assignmentMode =
            'MANUAL';

          break;
        }


        case 'ACCEPT':
        case 'ACCEPT_START': {
          if (
            current.statusCode !==
            'ASSIGNED'
          ) {
            throw new Error(
              '배정 상태의 오더만 접수할 수 있습니다.'
            );
          }

          if (
            isManager &&
            current
              .routeCandidateEmployeeNos
              .length > 1 &&
            current.routeLocked !== true
          ) {
            throw new Error(
              '공동 전달 오더는 하우스맨이 직접 접수해야 합니다.'
            );
          }

          const startImmediately =
            action === 'ACCEPT_START';

          updates['처리상태'] =
            startImmediately
              ? 'PROCESSING'
              : 'ACCEPTED';

          updates['접수일시'] = now;

          if (startImmediately) {
            updates['처리시작일시'] =
              now;
          }

          updates['처리자사번'] =
            user.employeeNo;

          if (role === 'HOUSEMAN') {

            const candidates =
              current
                .routeCandidateEmployeeNos
                .length
                ? current
                    .routeCandidateEmployeeNos
                : [
                    current
                      .assignedEmployeeNo
                  ].filter(Boolean);

            const releasedEmployeeNos =
              candidates.filter(
                employeeNo =>
                  employeeNo !==
                  user.employeeNo
              );

            updates['배정사번'] =
              user.employeeNo;

            updates['대상사번'] =
              user.employeeNo;

            updates['세부내용JSON'] =
              JSON.stringify(
                Object.assign(
                  {},
                  currentDetail,
                  {
                    routeLocked: true,

                    acceptedByEmployeeNo:
                      user.employeeNo,

                    acceptedAt: now,

                    startedAt:
                      startImmediately
                        ? now
                        : String(
                            currentDetail
                              .startedAt || ''
                          ),

                    releasedCandidateEmployeeNos:
                      releasedEmployeeNos
                  }
                )
              );

            auditDetail = {
              acceptedByEmployeeNo:
                user.employeeNo,

              releasedCandidateEmployeeNos:
                releasedEmployeeNos,

              startedImmediately:
                startImmediately
            };

          } else {

            auditDetail = {
              startedImmediately:
                startImmediately
            };
          }

          break;
        }


        case 'START':

          updates['처리상태'] =
            'PROCESSING';

          updates['처리시작일시'] =
            now;

          updates['처리자사번'] =
            user.employeeNo;

          break;


        case 'COMPLETE':

          updates['처리상태'] =
            'COMPLETED';

          updates['완료일시'] =
            now;

          updates['처리자사번'] =
            user.employeeNo;

          updates['처리불가사유'] =
            '';

          break;


        case 'UNABLE':

          updates['처리상태'] =
            'UNABLE';

          updates['완료일시'] =
            now;

          updates['처리자사번'] =
            user.employeeNo;

          updates['처리불가사유'] =
            String(
              payload.reason || ''
            ).trim();

          if (
            !updates['처리불가사유']
          ) {
            throw new Error(
              '처리불가 사유를 입력하세요.'
            );
          }

          break;


        case 'REOPEN':

          if (!isManager) {
            throw new Error(
              '오더 재개는 오더테이커만 가능합니다.'
            );
          }

          updates['처리상태'] =
            current.assignedEmployeeNo
              ? 'ASSIGNED'
              : 'REGISTERED';

          updates['완료일시'] =
            '';

          updates['처리불가사유'] =
            '';

          break;


        case 'EDIT': {

          if (!isManager) {
            throw new Error(
              '오더 수정은 오더테이커만 가능합니다.'
            );
          }

          const edited =
            normalizeHousemanPayload_(
              Object.assign(
                {},
                current,
                payload
              )
            );

          if (
            !edited.part ||
            !edited.items.length
          ) {
            throw new Error(
              '파트와 품목을 확인하세요.'
            );
          }

          const itemSummary =
            edited.items
              .map(item =>
                item.quantity > 1
                  ? `${item.name}×${item.quantity}`
                  : item.name
              )
              .join(', ');

          updates['파트'] =
            edited.part;

          updates['품목'] =
            itemSummary;

          updates['수량'] =
            edited.items.reduce(
              (sum, item) =>
                sum + item.quantity,
              0
            );

          updates['추가내용'] =
            edited.note;

          updates['요청자'] =
            edited.requester;

          updates['중요여부'] =
            edited.important
              ? 'Y'
              : 'N';

          updates['인수인계여부'] =
            edited.handover
              ? 'Y'
              : 'N';

          updates['세부내용JSON'] =
            JSON.stringify(
              Object.assign(
                {},
                currentDetail,
                {
                  items:
                    edited.items,

                  requester:
                    edited.requester,

                  requestSource:
                    edited.requestSource,

                  editedFrom:
                    'ORDER_DESKTOP',

                  handoverTargetShift:
                    edited.handover
                      ? (
                          current
                            .handoverTargetShift ||
                          resolveHandoverTargetShift_(
                            current
                              .registeredAt ||
                            now
                          )
                        )
                      : ''
                }
              )
            );

          auditDetail = {
            edited: true
          };

          break;
        }


        default:

          throw new Error(
            '지원하지 않는 오더 작업입니다.'
          );
      }

      const version =
        reserveDataVersion_({
          lockHeld: true
        });

      updates['변경버전'] =
        version;

      const newRow =
        found.row.slice();

      const headerMap =
        found.headerMap;

      Object.keys(updates)
        .forEach(header => {
          if (headerMap[header]) {
            newRow[
              headerMap[header] - 1
            ] = updates[header];
          }
        });

      sheet
        .getRange(
          found.rowNumber,
          1,
          1,
          newRow.length
        )
        .setValues([newRow]);

      publishDataVersion_(
        version,
        {
          domains: ['ORDER'],
          businessDate:
            current.businessDate,
          site:
            current.site,
          lockHeld: true
        }
      );

      const order =
        housemanOrderObject_(
          rowObjectFromValues_(
            newRow,
            headerMap
          ),
          found.rowNumber,
          usersByEmployeeNo,
          statusCodeMap
        );

      let telegramDispatch = {
        queued: false,
        queueRecordId: '',
        queueRowNumber: 0,
        reminderScheduled: false,
        reminderRecordId: ''
      };

      if (action === 'ASSIGN') {
        // 관리자 배정은 감사 + Telegram 큐를 한 번에 기록하고 즉시 응답합니다.
        // Telegram 네트워크 발송은 응답 후 dispatchHousemanOrderTelegramFast에서 처리합니다.
        const auxStartRow = sheet.getLastRow() + 1;
        const auditRow = buildHousemanAuditRow_(
          sheet,
          order,
          action,
          user.employeeNo,
          version,
          auditDetail
        );
        const telegramPrepared = prepareHousemanOrderFastTelegramRows_(
          sheet,
          order,
          action,
          { firstRowNumber: auxStartRow + 1 }
        );
        const auxRows = [auditRow].concat(telegramPrepared.rows || []);
        ensureSheetRowCapacity_(sheet, auxStartRow + auxRows.length - 1);
        sheet.getRange(
          auxStartRow,
          1,
          auxRows.length,
          sheet.getLastColumn()
        ).setValues(auxRows);
        telegramDispatch = {
          queued: Boolean(telegramPrepared.queueRecordId),
          queueRecordId: telegramPrepared.queueRecordId || '',
          queueRowNumber: Number(telegramPrepared.queueRowNumber || 0),
          reminderScheduled: Boolean(telegramPrepared.reminderRecordId),
          reminderRecordId: telegramPrepared.reminderRecordId || ''
        };
      } else {
        appendHousemanAudit_(
          order,
          action,
          user.employeeNo,
          version,
          auditDetail
        );
      }

      return {
        ok: true,
        version,
        order,
        telegram: telegramDispatch
      };

    } finally {
      writeLock.releaseLock();
    }
  });
}


function assignHousemanOrderFast(token, payload) { // (관리자 미배정 오더 수동배정 고속 저장)
  return measureResponse_('assignHousemanOrderFast', () => {
    const startedMs = Date.now();
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');

    const user = auth.user;
    const role = String(user.role || '').trim().toUpperCase();
    if (!['ADMIN', 'ORDER'].includes(role)) {
      throw new Error('직원배정은 오더테이커만 가능합니다.');
    }

    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    const employeeNo = String(safe.employeeNo || '').trim();
    const preferredRowNumber = Number(safe.rowNumber || 0);
    if (!orderId) throw new Error('오더 번호가 없습니다.');
    if (!employeeNo) throw new Error('배정 직원을 선택하세요.');

    const assigned = getActiveUserByEmployeeNo_(employeeNo);
    if (!assigned || assigned.role !== 'HOUSEMAN') {
      throw new Error('사용 가능한 하우스맨 계정이 아닙니다.');
    }

    const lock = LockService.getScriptLock();
    const lockStartedMs = Date.now();
    if (!lock.tryLock(Number(NOVA.WRITE_LOCK_TIMEOUT_MS || 2500))) {
      const busyError = new Error('동시 오더 처리가 많습니다. 잠시 후 다시 처리하세요.');
      busyError.code = 'BUSY_RETRY';
      throw busyError;
    }
    const lockWaitMs = Math.max(0, Date.now() - lockStartedMs);

    let findMs = 0;
    let writeMs = 0;
    let versionMs = 0;
    let publishMs = 0;

    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const findStartedMs = Date.now();
      const found = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
      findMs = Math.max(0, Date.now() - findStartedMs);
      if (!found) throw new Error('하우스맨 오더를 찾을 수 없습니다.');

      const currentVersion = Number(found.data['변경버전'] || 0);
      assertExpectedVersion_(safe.expectedVersion, currentVersion, `오더 ${orderId}`);

      let detail = {};
      try {
        detail = JSON.parse(String(found.data['세부내용JSON'] || '{}'));
      } catch (_) {
        detail = {};
      }

      const now = nowText_();
      const assignDetail = Object.assign({}, detail, {
        assignmentMode: 'MANUAL',
        autoAssigned: false,
        assignedBuilding: normalizeRoomBuilding_('', found.data['객실번호']),
        assignedShiftCode: '',
        assignedShiftCodes: [],
        routeCandidateEmployeeNos: [employeeNo],
        routeCandidateNames: [assigned.name || employeeNo],
        routeLocked: true,
        acceptedByEmployeeNo: '',
        releasedCandidateEmployeeNos: []
      });

      const versionStartedMs = Date.now();
      const version = reserveDataVersion_({ lockHeld: true });
      versionMs = Math.max(0, Date.now() - versionStartedMs);

      const newRow = found.row.slice();
      const headerMap = found.headerMap;
      const updates = {
        '대상사번': employeeNo,
        '처리상태': 'ASSIGNED',
        '세부내용JSON': JSON.stringify(assignDetail),
        '수정일시': now,
        '배정사번': employeeNo,
        '변경버전': version
      };
      Object.keys(updates).forEach(header => {
        if (headerMap[header]) newRow[headerMap[header] - 1] = updates[header];
      });

      const writeStartedMs = Date.now();
      sheet.getRange(found.rowNumber, 1, 1, newRow.length).setValues([newRow]);
      writeMs = Math.max(0, Date.now() - writeStartedMs);

      const publishStartedMs = Date.now();
      publishDataVersion_(version, {
        domains: ['ORDER'],
        businessDate: String(found.data['업무일자'] || '').trim(),
        site: String(found.data['사업장'] || '').trim(),
        lockHeld: true
      });
      publishMs = Math.max(0, Date.now() - publishStartedMs);

      const users = {};
      users[employeeNo] = assigned;
      const order = housemanOrderObject_(
        rowObjectFromValues_(newRow, headerMap),
        found.rowNumber,
        users,
        { ASSIGNED: '배정' }
      );

      return {
        ok: true,
        version,
        order,
        telegram: { queued: false, deferred: true },
        timing: {
          lockWaitMs,
          findMs,
          versionMs,
          writeMs,
          publishMs,
          totalMs: Math.max(0, Date.now() - startedMs)
        }
      };
    } finally {
      lock.releaseLock();
    }
  });
}


function finalizeHousemanAssignmentAux(token, payload) { // (수동배정 감사·Telegram 후속 저장)
  const auth = verifyNovaToken(token);
  if (!auth.ok) throw new Error('로그인이 필요합니다.');

  const user = auth.user;
  const role = String(user.role || '').trim().toUpperCase();
  if (!['ADMIN', 'ORDER'].includes(role)) {
    throw new Error('직원배정 후속처리 권한이 없습니다.');
  }

  const safe = payload || {};
  const orderId = String(safe.orderId || '').trim();
  const employeeNo = String(safe.employeeNo || '').trim();
  const version = Number(safe.version || 0);
  const rowNumber = Number(safe.rowNumber || 0);
  if (!orderId || !employeeNo || !version) {
    throw new Error('배정 후속처리 정보가 부족합니다.');
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(Number(NOVA.WRITE_LOCK_TIMEOUT_MS || 2500))) {
    const busyError = new Error('배정 후속처리가 지연되고 있습니다.');
    busyError.code = 'BUSY_RETRY';
    throw busyError;
  }

  try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const found = findHousemanOrderRow_(sheet, orderId, rowNumber);
    if (!found) throw new Error('하우스맨 오더를 찾을 수 없습니다.');

    const storedVersion = Number(found.data['변경버전'] || 0);
    const storedEmployeeNo = String(found.data['배정사번'] || found.data['대상사번'] || '').trim();
    const storedStatus = String(found.data['처리상태'] || '').trim().toUpperCase();
    if (storedVersion !== version || storedEmployeeNo !== employeeNo || storedStatus !== 'ASSIGNED') {
      return { ok: true, skipped: true, reason: 'STALE_ASSIGNMENT' };
    }

    const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
    const statusCodeMap = {};
    getCodes_('하우스맨상태').forEach(code => { statusCodeMap[code.code] = code.label; });
    const order = housemanOrderObject_(
      found.data,
      found.rowNumber,
      usersByEmployeeNo,
      statusCodeMap
    );

    const auxStartRow = sheet.getLastRow() + 1;
    const auditRow = buildHousemanAuditRow_(
      sheet,
      order,
      'ASSIGN',
      user.employeeNo,
      version,
      { employeeNo, assignmentMode: 'MANUAL', fastAssignment: true }
    );
    const telegramPrepared = prepareHousemanOrderFastTelegramRows_(
      sheet,
      order,
      'ASSIGN',
      { firstRowNumber: auxStartRow + 1 }
    );
    const auxRows = [auditRow].concat(telegramPrepared.rows || []);
    ensureSheetRowCapacity_(sheet, auxStartRow + auxRows.length - 1);
    sheet.getRange(auxStartRow, 1, auxRows.length, sheet.getLastColumn()).setValues(auxRows);

    return {
      ok: true,
      telegram: {
        queued: Boolean(telegramPrepared.queueRecordId),
        queueRecordId: telegramPrepared.queueRecordId || '',
        queueRowNumber: Number(telegramPrepared.queueRowNumber || 0),
        reminderScheduled: Boolean(telegramPrepared.reminderRecordId),
        reminderRecordId: telegramPrepared.reminderRecordId || ''
      }
    };
  } finally {
    lock.releaseLock();
  }
}


function getHousemanOrdersForDate_(
  businessDate,
  site,
  usersByEmployeeNo,
  statusCodeMap
) { // (업무일자 처리현황 조회·변경버전 단기 캐시)

  const orderVersion =
    getSyncVersion_(
      ['ORDER'],
      businessDate,
      site
    );

  const cacheKey =
    buildDeltaCacheKey_(
      'HOUSEMAN_ORDERS',
      [
        businessDate,
        site,
        orderVersion
      ]
    );

  const cached =
    getCachedJson_(cacheKey);

  if (cached) {
    return cached;
  }

  const sheet =
    getRequiredSheet_(
      NOVA.SHEETS.HISTORY
    );

  if (sheet.getLastRow() < 2) {
    return [];
  }

  const headerMap =
    getHeaderMap_(sheet);

  const scanLimit = 3000;

  const startRow =
    Math.max(
      2,
      sheet.getLastRow()
        - scanLimit
        + 1
    );

  const rowCount =
    sheet.getLastRow()
      - startRow
      + 1;

  const values =
    sheet
      .getRange(
        startRow,
        1,
        rowCount,
        sheet.getLastColumn()
      )
      .getDisplayValues();

  const result =
    values
      .map(
        (row, offset) => ({
          row,
          rowNumber:
            startRow + offset,

          data:
            rowObjectFromValues_(
              row,
              headerMap
            )
        })
      )
      .filter(
        item =>
          item.data['기록구분']
            ===
          NOVA.RECORD_TYPES
            .HOUSEMAN_ORDER
      )
      .filter(
        item =>
          String(
            item.data['업무일자']
            || ''
          ).trim()
            ===
          businessDate
      )
      .filter(
        item =>
          !site ||
          String(
            item.data['사업장']
            || ''
          ).trim()
            ===
          site
      )
      .filter(
        item =>
          String(
            item.data['삭제여부']
            || 'N'
          )
            .toUpperCase()
            !== 'Y'
      )
      .map(
        item =>
          housemanOrderObject_(
            item.data,
            item.rowNumber,
            usersByEmployeeNo,
            statusCodeMap
          )
      )
      .sort(
        (a, b) =>
          String(b.updatedAt)
            .localeCompare(
              String(a.updatedAt)
            )
          ||
          String(b.registeredAt)
            .localeCompare(
              String(a.registeredAt)
            )
      );

  putCachedJson_(
    cacheKey,
    result,
    NOVA.DELTA_CACHE_SECONDS
  );

  return result;
}


function findHousemanOrderRow_(
  sheet,
  orderId,
  preferredRowNumber
) { // (오더 행번호 우선 단건 조회·불일치 시 ID 검색)

  const headerMap =
    getHeaderMap_(sheet);

  const idColumn =
    headerMap['기록ID'];

  const lastRow =
    sheet.getLastRow();

  if (
    !idColumn ||
    lastRow < 2
  ) {
    return null;
  }

  const directRowNumber =
    Number(
      preferredRowNumber || 0
    );

  if (
    Number.isInteger(
      directRowNumber
    )
    &&
    directRowNumber >= 2
    &&
    directRowNumber <= lastRow
  ) {

    const directRow =
      sheet
        .getRange(
          directRowNumber,
          1,
          1,
          sheet.getLastColumn()
        )
        .getDisplayValues()[0];

    const directData =
      rowObjectFromValues_(
        directRow,
        headerMap
      );

    if (
      String(
        directData['기록ID']
        || ''
      ).trim() === orderId
      &&
      directData['기록구분']
        ===
      NOVA.RECORD_TYPES
        .HOUSEMAN_ORDER
    ) {

      return {
        rowNumber:
          directRowNumber,

        row:
          directRow,

        data:
          directData,

        headerMap
      };
    }
  }

  const finder =
    sheet
      .getRange(
        2,
        idColumn,
        lastRow - 1,
        1
      )
      .createTextFinder(
        orderId
      )
      .matchEntireCell(true);

  const cell =
    finder.findNext();

  if (!cell) {
    return null;
  }

  const rowNumber =
    cell.getRow();

  const row =
    sheet
      .getRange(
        rowNumber,
        1,
        1,
        sheet.getLastColumn()
      )
      .getDisplayValues()[0];

  const data =
    rowObjectFromValues_(
      row,
      headerMap
    );

  if (
    data['기록구분']
      !==
    NOVA.RECORD_TYPES
      .HOUSEMAN_ORDER
  ) {
    return null;
  }

  return {
    rowNumber,
    row,
    data,
    headerMap
  };
}


function housemanOrderObject_(
  data,
  rowNumber,
  usersByEmployeeNo,
  providedStatusCodeMap
) { // (오더 화면 객체 변환)

  const users =
    usersByEmployeeNo ||
    getUserIndex_().byEmployeeNo;

  const statusCode =
    String(
      data['처리상태']
      || 'REGISTERED'
    )
      .trim()
      .toUpperCase();

  const statusCodeMap =
    providedStatusCodeMap || {};

  if (!providedStatusCodeMap) {

    getCodes_(
      '하우스맨상태'
    ).forEach(code => {
      statusCodeMap[code.code] =
        code.label;
    });
  }

  let detail = {};

  try {
    detail = JSON.parse(
      String(
        data['세부내용JSON']
        || '{}'
      )
    );
  } catch (error) {
    detail = {};
  }

  const items =
    Array.isArray(
      detail.items
    )
    &&
    detail.items.length

      ? detail.items.map(
          item => ({
            name:
              String(
                item.name || ''
              ).trim(),

            quantity:
              Math.max(
                1,
                Number(
                  item.quantity || 1
                )
              )
          })
        )

      : String(
          data['품목'] || ''
        )
          .split(',')
          .filter(Boolean)
          .map(
            name => ({
              name:
                name.trim(),

              quantity:
                1
            })
          );

  const assignedEmployeeNo =
    String(
      data['배정사번']
      ||
      data['대상사번']
      ||
      ''
    ).trim();

  const processorEmployeeNo =
    String(
      data['처리자사번']
      ||
      ''
    ).trim();

  const hasRouteCandidateField =
    Array.isArray(
      detail.routeCandidateEmployeeNos
    );

  const routeCandidateEmployeeNos =
    Array.from(
      new Set(
        (
          hasRouteCandidateField
            ? detail
                .routeCandidateEmployeeNos
            : []
        )
          .map(String)
          .map(
            value =>
              value.trim()
          )
          .filter(Boolean)
      )
    );

  const storedCandidateNames =
    Array.isArray(
      detail.routeCandidateNames
    )
      ? detail.routeCandidateNames
      : [];

  const routeCandidateNames =
    routeCandidateEmployeeNos
      .map(
        (
          employeeNo,
          index
        ) =>
          users[employeeNo]
            ? users[
                employeeNo
              ].name
            : String(
                storedCandidateNames[
                  index
                ]
                ||
                employeeNo
              ).trim()
      );

  const routeLocked =
    detail.routeLocked === true
    ||
    !hasRouteCandidateField;

  return {

    rowNumber,

    orderId:
      String(
        data['기록ID']
        || ''
      ).trim(),

    businessDate:
      String(
        data['업무일자']
        || ''
      ).trim(),

    site:
      String(
        data['사업장']
        || ''
      ).trim(),

    roomNo:
      String(
        data['객실번호']
        || ''
      ).trim(),

    part:
      String(
        data['파트']
        || ''
      ).trim(),

    items,

    itemSummary:
      String(
        data['품목']
        || ''
      ).trim(),

    quantity:
      Number(
        data['수량']
        || 0
      ),

    note:
      String(
        data['추가내용']
        || ''
      ).trim(),

    requester:
      String(
        data['요청자']
        ||
        detail.requester
        ||
        ''
      ).trim(),

    assignedEmployeeNo,

    assignedName:
      users[
        assignedEmployeeNo
      ]
        ? users[
            assignedEmployeeNo
          ].name
        : '',

    processorEmployeeNo,

    processorName:
      users[
        processorEmployeeNo
      ]
        ? users[
            processorEmployeeNo
          ].name
        : '',

    statusCode,

    statusLabel:
      statusCodeMap[
        statusCode
      ]
      ||
      statusCode,

    important:
      String(
        data['중요여부']
        || ''
      )
        .toUpperCase()
        === 'Y',

    handover:
      String(
        data['인수인계여부']
        || ''
      )
        .toUpperCase()
        === 'Y',

    handoverTargetShift:
      String(
        detail
          .handoverTargetShift
        || ''
      )
        .trim()
        .toUpperCase()
      ||
      (
        String(
          data[
            '인수인계여부'
          ]
          || ''
        )
          .toUpperCase()
          === 'Y'

          ? resolveHandoverTargetShift_(
              data['등록일시']
            )

          : ''
      ),

    assignmentMode:
      String(
        detail.assignmentMode
        ||
        (
          assignedEmployeeNo
            ? 'MANUAL'
            : 'UNASSIGNED'
        )
      )
        .trim()
        .toUpperCase(),

    autoAssigned:
      detail.autoAssigned === true,

    assignedBuilding:
      String(
        detail.assignedBuilding
        ||
        normalizeRoomBuilding_(
          '',
          data['객실번호']
        )
      ).trim(),

    assignedShiftCode:
      String(
        detail.assignedShiftCode
        || ''
      )
        .trim()
        .toUpperCase(),

    assignedShiftCodes:
      Array.from(
        new Set(
          (
            Array.isArray(
              detail
                .assignedShiftCodes
            )
              ? detail
                  .assignedShiftCodes
              : [
                  detail
                    .assignedShiftCode
                ]
          )
            .map(String)
            .map(
              value =>
                value
                  .trim()
                  .toUpperCase()
            )
            .filter(Boolean)
        )
      ),

    routeCandidateEmployeeNos,

    routeCandidateNames,

    routeCandidateSummary:
      routeCandidateNames
        .join(' · '),

    routeLocked,

    acceptedByEmployeeNo:
      String(
        detail
          .acceptedByEmployeeNo
        || ''
      ).trim(),

    releasedCandidateEmployeeNos:
      Array.isArray(
        detail
          .releasedCandidateEmployeeNos
      )
        ? detail
            .releasedCandidateEmployeeNos
            .map(String)
            .map(
              value =>
                value.trim()
            )
            .filter(Boolean)
        : [],

    registeredBy:
      String(
        data['등록사번']
        || ''
      ).trim(),

    registeredAt:
      String(
        data['등록일시']
        || ''
      ).trim(),

    acceptedAt:
      String(
        data['접수일시']
        || ''
      ).trim(),

    startedAt:
      String(
        data['처리시작일시']
        || ''
      ).trim(),

    completedAt:
      String(
        data['완료일시']
        || ''
      ).trim(),

    unableReason:
      String(
        data['처리불가사유']
        || ''
      ).trim(),

    updatedAt:
      String(
        data['수정일시']
        ||
        data['등록일시']
        ||
        ''
      ).trim(),

    version:
      Number(
        data['변경버전']
        || 0
      )
  };
}


function normalizeHousemanPayload_(payload) { // (오더 입력값 정리)

  const safe =
    payload || {};

  let items =
    Array.isArray(
      safe.items
    )
      ? safe.items
      : [];

  if (
    !items.length
    &&
    safe.itemSummary
  ) {
    items =
      String(
        safe.itemSummary
      )
        .split(',')
        .map(
          name => ({
            name,
            quantity: 1
          })
        );
  }

  items =
    items
      .map(
        item => ({
          name:
            String(
              item
              &&
              item.name
              ||
              ''
            ).trim(),

          quantity:
            Math.max(
              1,
              Math.min(
                99,
                Number(
                  item
                  &&
                  item.quantity
                  ||
                  1
                )
              )
            )
        })
      )
      .filter(
        item =>
          item.name
      );

  return {

    businessDate:
      normalizeBusinessDate_(
        safe.businessDate
      ),

    site:
      String(
        safe.site || ''
      ).trim(),

    roomNo:
      String(
        safe.roomNo || ''
      ).trim(),

    part:
      String(
        safe.part || ''
      ).trim(),

    items,

    note:
      String(
        safe.note || ''
      ).trim(),

    requester:
      String(
        safe.requester
        || '오더테이커'
      ).trim(),

    requestSource:
      String(
        safe.requestSource
        || 'ORDER'
      ).trim(),

    assignedEmployeeNo:
      String(
        safe.assignedEmployeeNo
        ||
        safe.employeeNo
        ||
        ''
      ).trim(),

    assignmentMode: (() => {

      const mode =
        String(
          safe.assignmentMode
          || ''
        )
          .trim()
          .toUpperCase();

      if (
        mode === 'AUTO'
        ||
        mode === 'UNASSIGNED'
        ||
        mode === 'MANUAL'
      ) {
        return mode;
      }

      return String(
        safe.assignedEmployeeNo
        ||
        safe.employeeNo
        ||
        ''
      ).trim()
        ? 'MANUAL'
        : 'UNASSIGNED';

    })(),

    important:
      safe.important === true
      ||
      String(
        safe.important
        || ''
      ).toUpperCase()
        === 'Y',

    handover:
      safe.handover === true
      ||
      String(
        safe.handover
        || ''
      ).toUpperCase()
        === 'Y',

    // Realtime 미러용 내부 필드.
    // 일반 화면 요청에는 값이 없어 기존 동작과 동일합니다.
    realtimeOrderId:
      /^HO-\d{8}-[A-Z0-9]{8,32}$/
        .test(
          String(
            safe.realtimeOrderId
            || ''
          )
            .trim()
            .toUpperCase()
        )
        ? String(
            safe.realtimeOrderId
            || ''
          )
            .trim()
            .toUpperCase()
        : '',

    realtimeAssignmentSnapshot:
      safe.realtimeAssignmentSnapshot
      &&
      typeof safe.realtimeAssignmentSnapshot
        === 'object'

        ? safe.realtimeAssignmentSnapshot
        : null
  };
}


function normalizeRealtimeHousemanAssignmentSnapshot_(
  businessDate,
  site,
  roomNo,
  snapshot
) { // (Realtime 선등록 자동배정값 안전 검증)

  const safe =
    snapshot || {};

  const building =
    normalizeRoomBuilding_(
      '',
      roomNo
    );

  const snapshotBuilding =
    String(
      safe.building || ''
    ).trim();

  if (
    snapshotBuilding
    &&
    snapshotBuilding !== building
  ) {
    throw new Error(
      'Realtime 담당동 정보가 현재 객실과 일치하지 않습니다.'
    );
  }

  const employeeNos =
    Array.from(
      new Set(
        (
          Array.isArray(
            safe.employeeNos
          )
            ? safe.employeeNos
            : []
        )
          .map(
            value =>
              String(
                value || ''
              ).trim()
          )
          .filter(Boolean)
      )
    );

  const selectedEmployeeNo =
    String(
      safe.employeeNo
      ||
      employeeNos[0]
      ||
      ''
    ).trim();

  if (
    !selectedEmployeeNo
    ||
    !employeeNos.includes(
      selectedEmployeeNo
    )
  ) {
    throw new Error(
      `${building} 담당 하우스맨 정보를 다시 확인하세요.`
    );
  }

  const users =
    getUserIndex_()
      .byEmployeeNo;

  const names =
    employeeNos.map(
      employeeNo => {

        const user =
          users[employeeNo];

        if (
          !user
          ||
          !user.enabled
          ||
          user.role !== 'HOUSEMAN'
        ) {
          throw new Error(
            '사용 가능한 하우스맨 계정이 아닙니다.'
          );
        }

        return (
          user.name
          ||
          employeeNo
        );
      }
    );

  const selectedIndex =
    employeeNos.indexOf(
      selectedEmployeeNo
    );

  const currentShift =
    ['A', 'B', 'C'].includes(
      String(
        safe.currentShift || ''
      )
        .trim()
        .toUpperCase()
    )
      ? String(
          safe.currentShift || ''
        )
          .trim()
          .toUpperCase()

      : resolveCurrentShiftCode_(
          new Date()
        );

  const activeShiftCodes =
    Array.from(
      new Set(
        (
          Array.isArray(
            safe.activeShiftCodes
          )
            ? safe.activeShiftCodes
            : []
        )
          .map(
            value =>
              String(
                value || ''
              )
                .trim()
                .toUpperCase()
          )
          .filter(
            value =>
              [
                'A',
                'B',
                'C'
              ].includes(value)
          )
      )
    );

  return {

    building,

    employeeNo:
      selectedEmployeeNo,

    name:
      names[selectedIndex]
      ||
      selectedEmployeeNo,

    employeeNos,

    names,

    candidates:
      employeeNos.map(
        (
          employeeNo,
          index
        ) => ({
          employeeNo,
          name:
            names[index]
        })
      ),

    shiftCodes: [],

    pendingCount: 0,

    currentShift,

    activeShiftCodes:
      activeShiftCodes.length
        ? activeShiftCodes
        : [currentShift]
  };
}


function buildHousemanAuditRow_(
  sheet,
  order,
  action,
  employeeNo,
  version,
  detail
) { // (오더 감사이력 행 생성)

  const now =
    nowText_();

  return createRowByHeaders_(
    sheet,
    {
      '기록ID':
        `${NOVA.RECORD_TYPES.HOUSEMAN_AUDIT}-${Utilities.getUuid()}`,

      '기록구분':
        NOVA.RECORD_TYPES.HOUSEMAN_AUDIT,

      '업무일자':
        order.businessDate,

      '사업장':
        order.site,

      '객실번호':
        order.roomNo,

      '대상사번':
        order.assignedEmployeeNo,

      '처리상태':
        action,

      '세부내용JSON':
        JSON.stringify(
          Object.assign(
            {
              parentOrderId:
                order.orderId,

              statusCode:
                order.statusCode
            },
            detail || {}
          )
        ),

      '등록사번':
        employeeNo,

      '등록일시':
        now,

      '수정일시':
        now,

      '변경버전':
        version
        ||
        getDataVersion_(),

      '삭제여부':
        'N'
    }
  );
}


function appendHousemanAudit_(
  order,
  action,
  employeeNo,
  version,
  detail
) { // (오더 변경이력 추가)

  const sheet =
    getRequiredSheet_(
      NOVA.SHEETS.HISTORY
    );

  const row =
    buildHousemanAuditRow_(
      sheet,
      order,
      action,
      employeeNo,
      version,
      detail
    );

  const rowNumber =
    sheet.getLastRow() + 1;

  ensureSheetRowCapacity_(
    sheet,
    rowNumber
  );

  sheet
    .getRange(
      rowNumber,
      1,
      1,
      row.length
    )
    .setValues([row]);
}