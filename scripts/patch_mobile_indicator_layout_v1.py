from pathlib import Path
import re
import sys

MARKER = 'MOBILE_INDICATOR_LAYOUT_V1'
client_path = Path('Client.html')
styles_path = Path('Styles.html')

client = client_path.read_text(encoding='utf-8')
styles = styles_path.read_text(encoding='utf-8')

changed = False

if MARKER not in client:
    pattern = re.compile(
        r'''(<div class="control-group">\s*<span class="control-label">사업장</span>\s*<select id="indicatorSite">.*?</select>)\s*<button id="indicatorQueryButton" class="filter-button primary-inline" type="button">조회하기</button>\s*</div>''',
        re.S
    )
    match = pattern.search(client)
    if not match:
        print('ERROR: indicator site/query layout anchor not found.', file=sys.stderr)
        sys.exit(70)
    replacement = (
        match.group(1)
        + '\n            </div>\n'
        + '            <div class="indicator-query-row">\n'
        + '              <button id="indicatorQueryButton" class="filter-button primary-inline" type="button">조회하기</button>\n'
        + '            </div> <!-- MOBILE_INDICATOR_LAYOUT_V1 -->'
    )
    client = client[:match.start()] + replacement + client[match.end():]
    changed = True

if MARKER not in styles:
    css = r'''

  /* MOBILE_INDICATOR_LAYOUT_V1
   * 모바일 통합 인디케이터 상단: 업무일자·사업장 2열 + 조회하기 전체폭.
   * 로그인 안내문구는 작은 글씨로 최대 2줄만 표시합니다.
   */
  .indicator-query-row {
    display: flex;
    align-items: end;
  }
  .indicator-query-row #indicatorQueryButton {
    min-width: 96px;
    white-space: nowrap;
  }

  @media (max-width: 760px) {
    #loginView .login-card .login-guide {
      margin: 0 auto 12px;
      max-width: 100%;
      font-size: 11px;
      line-height: 1.35;
      letter-spacing: -0.35px;
      color: var(--muted);
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
      overflow: hidden;
    }

    .indicator-page .indicator-controls {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 10px;
      align-items: end;
    }

    .indicator-page .indicator-controls > .control-group:nth-of-type(1),
    .indicator-page .indicator-controls > .control-group:nth-of-type(2) {
      min-width: 0;
      width: 100%;
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 6px;
    }

    .indicator-page .indicator-controls > .control-group:nth-of-type(1) .control-label,
    .indicator-page .indicator-controls > .control-group:nth-of-type(2) .control-label {
      font-size: 12px;
      line-height: 1.2;
      font-weight: 800;
      margin: 0;
    }

    .indicator-page #indicatorDate,
    .indicator-page #indicatorSite {
      width: 100%;
      min-width: 0;
      height: 50px;
      padding: 0 12px;
      border-radius: 13px;
      font-size: 15px;
    }

    .indicator-page .indicator-query-row {
      grid-column: 1 / -1;
      width: 100%;
    }

    .indicator-page .indicator-query-row #indicatorQueryButton {
      width: 100%;
      min-width: 0;
      height: 50px;
      padding: 0 16px;
      border-radius: 13px;
      font-size: 15px;
      font-weight: 800;
      line-height: 1;
      white-space: nowrap;
    }

    .indicator-page #roomSearch,
    .indicator-page #roomUploadButton,
    .indicator-page #indicatorSummary {
      grid-column: 1 / -1;
      width: 100%;
    }

    .indicator-page #roomSearch {
      min-width: 0;
      height: 50px;
      border-radius: 13px;
    }

    .indicator-page #roomUploadButton {
      min-height: 50px;
      border-radius: 13px;
    }
  }
'''
    idx = styles.rfind('</style>')
    if idx < 0:
        print('ERROR: Styles.html closing </style> not found.', file=sys.stderr)
        sys.exit(71)
    styles = styles[:idx] + css + '\n' + styles[idx:]
    changed = True

if changed:
    client_path.write_text(client, encoding='utf-8')
    styles_path.write_text(styles, encoding='utf-8')
    print('Applied mobile indicator layout optimization V1.')
else:
    print('Mobile indicator layout optimization V1 already applied.')
