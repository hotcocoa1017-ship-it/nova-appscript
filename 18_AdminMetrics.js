/**
 * NOVA v1.0 RC6.3 관리자 전용 운영성과지표
 * 기존 업무이력만 사용하여 하우스맨 처리성과와 룸메이드 정비·수검 품질을 집계합니다.
 */
function getAdminOperationsMetrics(token, filters) { // (관리자 전용 운영성과지표 조회)
  return measureResponse_('getAdminOperationsMetrics', () => {
    const user = requireRole_(token, ['ADMIN']);
    const request = normalizeAdminMetricsFilters_(filters);
    const rows = readMonthlyHistoryRows_(request, [NOVA.RECORD_TYPES.HOUSEMAN_ORDER, NOVA.RECORD_TYPES.CLEANING, NOVA.RECORD_TYPES.QM_CHECKLIST])
      .map(row => row && row.data ? row.data : row);
    return Object.assign({ ok: true, filters: request, serverTime: nowText_() }, buildAdminOperationsMetrics_(rows, request));
  });
}

function normalizeAdminMetricsFilters_(filters) { // (운영성과 조회조건 정리)
  const safe = filters || {};
  const now = new Date();
  const period = String(safe.period || 'MONTHLY').toUpperCase() === 'DAILY' ? 'DAILY' : 'MONTHLY';
  const date = normalizeMonthlyDate_(safe.date, Number(safe.year || Utilities.formatDate(now, NOVA.TIMEZONE, 'yyyy')), Number(safe.month || Utilities.formatDate(now, NOVA.TIMEZONE, 'M')));
  return {
    period,
    date,
    year: period === 'DAILY' ? Number(date.slice(0, 4)) : Math.max(2020, Math.min(2100, Number(safe.year || Utilities.formatDate(now, NOVA.TIMEZONE, 'yyyy')))),
    month: period === 'DAILY' ? Number(date.slice(5, 7)) : Math.max(1, Math.min(12, Number(safe.month || Utilities.formatDate(now, NOVA.TIMEZONE, 'M')))),
    site: String(safe.site || '').trim()
  };
}

function buildAdminOperationsMetrics_(rows, request) { // (운영성과 전체 집계)
  const users = getUserIndex_().byEmployeeNo;
  const houseman = {};
  const cleaningEvents = {};
  const inspections = {};
  const sites = new Set();
  (rows || []).forEach(data => {
    const site = String(data['사업장'] || '').trim();
    if (request.site && site !== request.site) return;
    if (site) sites.add(site);
    const type = String(data['기록구분'] || '').trim();
    if (type === NOVA.RECORD_TYPES.HOUSEMAN_ORDER) applyHousemanMetric_(houseman, data, users);
    if (type === NOVA.RECORD_TYPES.CLEANING) collectCleaningMetric_(cleaningEvents, data);
    if (type === NOVA.RECORD_TYPES.QM_CHECKLIST) collectInspectionMetric_(inspections, data);
  });
  const roommaid = buildRoommaidAdminMetrics_(cleaningEvents, inspections, users);
  const hmRows = Object.values(houseman).map(finalizeHousemanMetric_).sort((a,b)=>b.processedOrders-a.processedOrders||a.name.localeCompare(b.name,'ko'));
  const hmDurations = hmRows.flatMap(row => row._durations || []);
  hmRows.forEach(row => delete row._durations);
  return {
    summary: {
      housemanProcessed: hmRows.reduce((s,r)=>s+r.processedOrders,0),
      housemanAverageMinutes: averageMetric_(hmDurations),
      roommaidAverageDailyUnits: roommaid.summary.averageDailyUnits,
      roommaidAverageDailyInspections: roommaid.summary.averageDailyInspections,
      roommaidDefectRate: roommaid.summary.defectRate
    },
    housemanRows: hmRows,
    roommaidRows: roommaid.rows,
    cleaningTypeSummary: roommaid.cleaningTypeSummary,
    options: { sites: Array.from(sites).filter(Boolean).sort((a,b)=>a.localeCompare(b,'ko')) }
  };
}

function applyHousemanMetric_(map, data, users) { // (하우스맨 1건 집계)
  const status = String(data['처리상태'] || '').trim().toUpperCase();
  if (!['COMPLETED','UNABLE'].includes(status)) return;
  const no = String(data['처리자사번'] || data['배정사번'] || data['대상사번'] || '').trim();
  if (!no) return;
  if (!map[no]) map[no] = { employeeNo:no, name:(users[no]&&users[no].name)||no, processedOrders:0, completed:0, unable:0, _durations:[] };
  const g=map[no]; g.processedOrders += 1; if(status==='COMPLETED') g.completed += 1; else g.unable += 1;
  const duration=minutesBetween_(String(data['처리시작일시']||data['접수일시']||data['등록일시']||''), String(data['완료일시']||''));
  if(Number.isFinite(duration)) g._durations.push(duration);
}
function finalizeHousemanMetric_(g) { return Object.assign({}, g, { averageMinutes: averageMetric_(g._durations) }); }

function collectCleaningMetric_(map, data) { // (룸메이드 시작·완료 이벤트 수집)
  const status=String(data['처리상태']||'').trim().toUpperCase();
  if(!['CLEANING_START','ROOMMAID_START','CLEANING_COMPLETE','ROOMMAID_COMPLETE'].includes(status)) return;
  let detail={}; try{detail=JSON.parse(String(data['세부내용JSON']||'{}'));}catch(e){}
  const date=String(data['업무일자']||'').trim(), site=String(data['사업장']||'').trim(), room=String(data['객실번호']||'').trim();
  const no=String(detail.primaryEmployeeNo||data['대상사번']||'').trim(); if(!date||!room||!no) return;
  const key=`${date}|${site}|${room}|${no}`; if(!map[key]) map[key]={date,site,room,no,start:'',complete:'',cleaningType:String(detail.cleaningType||NOVA.CLEANING_TYPES.NORMAL).toUpperCase(),unit:Number(detail.creditUnit!=null?detail.creditUnit:(String(detail.cleaningType||'').toUpperCase()===NOVA.CLEANING_TYPES.DS?getCleaningCreditUnit_(NOVA.CLEANING_TYPES.DS):1))};
  const at=String(data['완료일시']||data['처리시작일시']||data['수정일시']||data['등록일시']||'').trim();
  if(status.includes('START')) map[key].start=at; else map[key].complete=at;
}
function collectInspectionMetric_(map, data) { // (룸메이드 수검·불량 집계)
  const status=String(data['처리상태']||'').trim().toUpperCase(); if(!['PASS','FAIL'].includes(status)) return;
  let detail={}; try{detail=JSON.parse(String(data['세부내용JSON']||'{}'));}catch(e){}
  const date=String(data['업무일자']||'').trim();
  [String(detail.roommaidEmployeeNo||'').trim(), String(detail.secondaryRoommaidEmployeeNo||'').trim()].filter(Boolean).forEach(no=>{
    const key=`${date}|${no}`; if(!map[key]) map[key]={date,no,inspected:0,defects:0}; map[key].inspected += 1; if(status==='FAIL') map[key].defects += 1;
  });
}
function buildRoommaidAdminMetrics_(cleaningEvents, inspections, users) { // (룸메이드별 정비시간·일평균·수검품질)
  const groups={}, typeDurations={};
  Object.values(cleaningEvents).forEach(e=>{
    if(!groups[e.no]) groups[e.no]={employeeNo:e.no,name:(users[e.no]&&users[e.no].name)||e.no,activeDays:new Set(),recognizedUnits:0,normalCount:0,dsCount:0,normalDurations:[],dsDurations:[],inspected:0,defects:0};
    const g=groups[e.no]; g.activeDays.add(e.date); if(e.complete){g.recognizedUnits+=Number.isFinite(e.unit)?e.unit:0; if(e.cleaningType===NOVA.CLEANING_TYPES.DS)g.dsCount++;else g.normalCount++;}
    const d=minutesBetween_(e.start,e.complete); if(Number.isFinite(d)){ const arr=e.cleaningType===NOVA.CLEANING_TYPES.DS?g.dsDurations:g.normalDurations; arr.push(d); const key=e.cleaningType===NOVA.CLEANING_TYPES.DS?'D/S':'일반정비'; if(!typeDurations[key])typeDurations[key]=[]; typeDurations[key].push(d); }
  });
  Object.values(inspections).forEach(i=>{ if(!groups[i.no]) groups[i.no]={employeeNo:i.no,name:(users[i.no]&&users[i.no].name)||i.no,activeDays:new Set(),recognizedUnits:0,normalCount:0,dsCount:0,normalDurations:[],dsDurations:[],inspected:0,defects:0}; const g=groups[i.no]; g.activeDays.add(i.date); g.inspected+=i.inspected; g.defects+=i.defects; });
  const rows=Object.values(groups).map(g=>{const days=Math.max(1,g.activeDays.size); return {employeeNo:g.employeeNo,name:g.name,activeDays:g.activeDays.size,normalAverageMinutes:averageMetric_(g.normalDurations),dsAverageMinutes:averageMetric_(g.dsDurations),averageDailyUnits:roundMetric_(g.recognizedUnits/days),averageDailyInspections:roundMetric_(g.inspected/days),inspected:g.inspected,defects:g.defects,defectRate:g.inspected?roundMetric_(g.defects/g.inspected*100):0};}).sort((a,b)=>b.averageDailyUnits-a.averageDailyUnits||a.name.localeCompare(b.name,'ko'));
  const totalDays=rows.reduce((s,r)=>s+r.activeDays,0), totalUnits=Object.values(groups).reduce((s,g)=>s+g.recognizedUnits,0), totalInspected=rows.reduce((s,r)=>s+r.inspected,0), totalDefects=rows.reduce((s,r)=>s+r.defects,0);
  return { rows, summary:{averageDailyUnits:totalDays?roundMetric_(totalUnits/totalDays):0,averageDailyInspections:totalDays?roundMetric_(totalInspected/totalDays):0,defectRate:totalInspected?roundMetric_(totalDefects/totalInspected*100):0}, cleaningTypeSummary:Object.keys(typeDurations).map(type=>({type,count:typeDurations[type].length,averageMinutes:averageMetric_(typeDurations[type])})) };
}
function averageMetric_(values){ const valid=(values||[]).filter(Number.isFinite); return valid.length?roundMetric_(valid.reduce((s,v)=>s+v,0)/valid.length):null; }
function roundMetric_(value){ return Math.round(Number(value||0)*10)/10; }
