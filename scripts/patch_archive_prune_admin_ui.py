from pathlib import Path
import sys

path = Path('ArchiveAdminClient.html')
text = path.read_text(encoding='utf-8')
marker = 'ARCHIVE_PRUNE_ADMIN_STATUS_V1'

if marker in text:
    print('Archive prune admin status patch already applied.')
    sys.exit(0)


def replace_once(old, new, label, code):
    global text
    count = text.count(old)
    if count != 1:
        print(f'ERROR: {label} anchor count={count}', file=sys.stderr)
        sys.exit(code)
    text = text.replace(old, new, 1)


css_anchor = "  .nova-archive-status-line { display:flex; align-items:center; gap:8px; min-height:38px; }\n"
css_insert = css_anchor + """  .nova-archive-prune-summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:8px; margin-bottom:10px; }
  .nova-archive-prune-summary > div { border:1px solid #e5e7eb; border-radius:9px; padding:10px; min-width:0; background:#fafafa; }
  .nova-archive-prune-summary span { display:block; color:#6b7280; font-size:11px; margin-bottom:4px; }
  .nova-archive-prune-summary strong { display:block; color:#111827; font-size:15px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .nova-archive-prune-note { color:#6b7280; font-size:11px; }
  .nova-archive-prune-table { min-width:720px; }
  .nova-archive-prune-state { display:inline-flex; align-items:center; border-radius:999px; padding:3px 8px; font-size:11px; font-weight:800; background:#ecfdf5; color:#047857; }
  .nova-archive-prune-state.bad { background:#fef2f2; color:#b91c1c; }
"""
replace_once(css_anchor, css_insert, 'prune CSS', 80)

const_anchor = "  const ARCHIVE_MENU_LABEL_ = 'Archive 이력';\n"
replace_once(const_anchor, const_anchor + "  const ARCHIVE_PRUNE_ADMIN_STATUS_V1_ = true; // ARCHIVE_PRUNE_ADMIN_STATUS_V1\n", 'prune marker', 81)

bind_anchor = "  function bindArchiveMenu_() {\n"
helpers = """  function archiveFormatDateTime_(value) {
    const date = new Date(value || '');
    if (!Number.isFinite(date.getTime())) return '-';
    try {
      return new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      }).format(date);
    } catch (_) {
      return date.toLocaleString();
    }
  }

  function archiveSourceLabel_(value) {
    const source = String(value || '');
    if (source === 'CURRENT_ROOM_HISTORY') return '객실상태';
    if (source === 'WORK_HISTORY') return '업무이력';
    return source || '-';
  }

  function archivePruneStatusLabel_(value) {
    const status = String(value || '').toUpperCase();
    if (status === 'COMPLETED') return '완료';
    if (status === 'PASSED') return '검증완료';
    if (status === 'FAILED') return '실패';
    if (status === 'STARTED') return '진행중';
    return status || '-';
  }

""" + bind_anchor
replace_once(bind_anchor, helpers, 'prune helpers', 82)

panel_anchor = """        </div>
        <section class=\"nova-archive-panel\">
          <div class=\"nova-archive-filter-grid\">"""
panel_insert = """        </div>
        <section class=\"nova-archive-panel\">
          <div class=\"nova-archive-result-meta\">
            <strong>Hot DB 보존 관리</strong>
            <span id=\"novaArchivePrunePolicy\">30일 초과 자동 정리 · Storage 원본 유지</span>
          </div>
          <div id=\"novaArchivePruneSummary\" class=\"nova-archive-prune-summary\">
            <div><span>보존 기준</span><strong>-</strong></div>
            <div><span>누적 정리</span><strong>-</strong></div>
            <div><span>완료 배치</span><strong>-</strong></div>
            <div><span>현재 대기</span><strong>-</strong></div>
          </div>
          <div id=\"novaArchivePruneRuns\"><div class=\"nova-archive-loading\">Prune 실행 이력을 확인하고 있습니다.</div></div>
        </section>
        <section class=\"nova-archive-panel\">
          <div class=\"nova-archive-filter-grid\">"""
replace_once(panel_anchor, panel_insert, 'prune panel', 83)

current_anchor = """    const current = result?.current || {};
    const healthy = result?.healthy === true && current?.ok === true;"""
current_insert = """    const current = result?.current || {};
    const prune = result?.prune || {};
    const healthy = result?.healthy === true && current?.ok === true;"""
replace_once(current_anchor, current_insert, 'prune status payload', 84)

render_anchor = """      <div class=\"nova-archive-status-card\"><span>WORK_HISTORY 인덱스</span><strong>${archiveEscape_(current.workHistoryIndexRowsPast ?? '-')}</strong></div>`;
  }

  function renderArchiveStatusError_(message) {"""
render_insert = """      <div class=\"nova-archive-status-card\"><span>WORK_HISTORY 인덱스</span><strong>${archiveEscape_(current.workHistoryIndexRowsPast ?? '-')}</strong></div>`;
    renderArchivePrune_(prune);
  }

  function renderArchivePrune_(prune) {
    const summary = document.getElementById('novaArchivePruneSummary');
    const runsRoot = document.getElementById('novaArchivePruneRuns');
    const policy = document.getElementById('novaArchivePrunePolicy');
    if (!summary || !runsRoot) return;

    const retentionDays = Number(prune?.retentionDays || 30);
    const totalDeletedRows = Number(prune?.totalDeletedRows || 0);
    const completedBatches = Number(prune?.completedBatches || 0);
    const remainingCandidates = Number(prune?.remainingCandidates || 0);
    const failedRuns = Number(prune?.failedRuns || 0);
    if (policy) policy.textContent = `${retentionDays}일 초과 자동 정리 · Storage 원본 유지`;

    summary.innerHTML = `
      <div><span>보존 기준</span><strong>${archiveEscape_(retentionDays)}일</strong></div>
      <div><span>누적 정리</span><strong>${archiveEscape_(totalDeletedRows.toLocaleString('ko-KR'))}행</strong></div>
      <div><span>완료 배치</span><strong>${archiveEscape_(completedBatches.toLocaleString('ko-KR'))}개</strong></div>
      <div><span>현재 대기</span><strong>${archiveEscape_(remainingCandidates.toLocaleString('ko-KR'))}개</strong></div>`;

    const runs = Array.isArray(prune?.recentRuns) ? prune.recentRuns : [];
    if (!runs.length) {
      runsRoot.innerHTML = '<div class=\"nova-archive-empty\">아직 Prune 실행 이력이 없습니다.</div>';
      return;
    }

    runsRoot.innerHTML = `
      <div class=\"nova-archive-result-meta\">
        <span>최근 실행 ${archiveEscape_(runs.length)}건</span>
        <span class=\"nova-archive-prune-note\">${failedRuns > 0 ? `실패 ${archiveEscape_(failedRuns)}건 확인 필요` : '실패 이력 없음'}</span>
      </div>
      <div class=\"nova-archive-table-wrap\">
        <table class=\"nova-archive-table nova-archive-prune-table\">
          <thead><tr><th>처리시각</th><th>영업일</th><th>사업장</th><th>데이터</th><th>정리행</th><th>상태</th></tr></thead>
          <tbody>${runs.map(run => {
            const bad = String(run?.status || '').toUpperCase() === 'FAILED';
            return `<tr>
              <td>${archiveEscape_(archiveFormatDateTime_(run?.completed_at || run?.started_at))}</td>
              <td>${archiveEscape_(run?.business_date || '-')}</td>
              <td>${archiveEscape_(run?.site || '-')}</td>
              <td>${archiveEscape_(archiveSourceLabel_(run?.source_type))}</td>
              <td>${archiveEscape_(Number(run?.deleted_rows || 0).toLocaleString('ko-KR'))}</td>
              <td><span class=\"nova-archive-prune-state ${bad ? 'bad' : ''}\">${archiveEscape_(archivePruneStatusLabel_(run?.status))}</span></td>
            </tr>`;
          }).join('')}</tbody>
        </table>
      </div>`;
  }

  function renderArchiveStatusError_(message) {"""
replace_once(render_anchor, render_insert, 'prune render', 85)

error_anchor = """  function renderArchiveStatusError_(message) {
    const line = document.getElementById('novaArchiveStatusLine');
    if (line) line.innerHTML = `<span class=\"nova-archive-dot bad\"></span><span>${archiveEscape_(message)}</span>`;
  }"""
error_insert = """  function renderArchiveStatusError_(message) {
    const line = document.getElementById('novaArchiveStatusLine');
    if (line) line.innerHTML = `<span class=\"nova-archive-dot bad\"></span><span>${archiveEscape_(message)}</span>`;
    const runsRoot = document.getElementById('novaArchivePruneRuns');
    if (runsRoot) runsRoot.innerHTML = `<div class=\"nova-archive-empty\">${archiveEscape_(message)}</div>`;
  }"""
replace_once(error_anchor, error_insert, 'prune error state', 86)

if marker not in text or 'novaArchivePruneRuns' not in text or 'renderArchivePrune_' not in text:
    print('ERROR: Archive prune UI markers missing after patch', file=sys.stderr)
    sys.exit(87)

path.write_text(text, encoding='utf-8')
print('Applied Archive prune admin status UI patch.')
