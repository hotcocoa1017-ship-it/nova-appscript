from pathlib import Path
import re
import sys

MARKER = 'MOBILE_INDICATOR_LAYOUT_V1'
DESKTOP_MARKER = 'INDICATOR_DESKTOP_LAYOUT_V1'
DESKTOP_V2_MARKER = 'INDICATOR_DESKTOP_LAYOUT_V2'
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

if DESKTOP_MARKER not in styles:
    desktop_css = r'''

  /* INDICATOR_DESKTOP_LAYOUT_V1
   * 데스크탑 통합 인디케이터 상단은 업무일자 · 사업장 · 조회하기를 한 줄로 균형 배치합니다.
   * 조회 로직/이벤트는 변경하지 않고 배치와 크기만 정리합니다.
   */
  @media (min-width: 761px) {
    .indicator-page .indicator-controls {
      display: grid;
      grid-template-columns: minmax(220px, 0.9fr) minmax(220px, 0.9fr) 112px;
      column-gap: 14px;
      row-gap: 12px;
      align-items: end;
    }

    .indicator-page .indicator-controls > .control-group:nth-of-type(1),
    .indicator-page .indicator-controls > .control-group:nth-of-type(2) {
      width: 100%;
      min-width: 0;
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 7px;
    }

    .indicator-page .indicator-controls > .control-group:nth-of-type(1) .control-label,
    .indicator-page .indicator-controls > .control-group:nth-of-type(2) .control-label {
      margin: 0;
      font-size: 13px;
      line-height: 1.2;
      font-weight: 800;
    }

    .indicator-page #indicatorDate,
    .indicator-page #indicatorSite {
      width: 100%;
      min-width: 0;
      height: 46px;
      padding: 0 14px;
      border-radius: 12px;
    }

    .indicator-page .indicator-query-row {
      width: 112px;
      min-width: 112px;
      align-self: end;
    }

    .indicator-page .indicator-query-row #indicatorQueryButton {
      width: 112px;
      min-width: 112px;
      height: 46px;
      padding: 0 14px;
      border-radius: 12px;
      font-size: 14px;
      font-weight: 800;
      line-height: 1;
      white-space: nowrap;
    }

    .indicator-page #roomSearch,
    .indicator-page #roomUploadButton,
    .indicator-page #indicatorSummary {
      grid-column: 1 / -1;
    }
  }
'''
    idx = styles.rfind('</style>')
    if idx < 0:
        print('ERROR: Styles.html closing </style> not found.', file=sys.stderr)
        sys.exit(72)
    styles = styles[:idx] + desktop_css + '\n' + styles[idx:]
    changed = True

if DESKTOP_V2_MARKER not in styles:
    desktop_v2_css = r'''

  /* INDICATOR_DESKTOP_LAYOUT_V2
   * 데스크탑 상단 조회영역을 기존의 컴팩트한 업무일자 폭에 맞춥니다.
   * 업무일자 · 사업장 · 조회하기 · 검색을 한 줄에 배치하며 모바일 레이아웃은 유지합니다.
   */
  @media (min-width: 761px) {
    .indicator-page .indicator-controls {
      display: grid;
      grid-template-columns: 220px 220px 104px minmax(220px, 320px) minmax(0, 1fr);
      column-gap: 10px;
      row-gap: 12px;
      align-items: end;
    }

    .indicator-page .indicator-controls > .control-group:nth-of-type(1),
    .indicator-page .indicator-controls > .control-group:nth-of-type(2) {
      width: 220px;
      min-width: 220px;
      max-width: 220px;
      gap: 6px;
    }

    .indicator-page #indicatorDate,
    .indicator-page #indicatorSite {
      width: 220px;
      min-width: 220px;
      max-width: 220px;
      height: 40px;
      padding: 0 12px;
      border-radius: 9px;
      font-size: 13px;
    }

    .indicator-page .indicator-query-row {
      grid-column: 3;
      grid-row: 1;
      width: 104px;
      min-width: 104px;
      align-self: end;
    }

    .indicator-page .indicator-query-row #indicatorQueryButton {
      width: 104px;
      min-width: 104px;
      height: 40px;
      padding: 0 12px;
      border-radius: 9px;
      font-size: 13px;
    }

    .indicator-page #roomSearch {
      grid-column: 4;
      grid-row: 1;
      align-self: end;
      width: 100%;
      min-width: 220px;
      max-width: 320px;
      height: 40px;
      margin: 0;
      border-radius: 9px;
      font-size: 13px;
    }

    .indicator-page #roomUploadButton,
    .indicator-page #indicatorSummary {
      grid-column: 1 / -1;
    }
  }
'''
    idx = styles.rfind('</style>')
    if idx < 0:
        print('ERROR: Styles.html closing </style> not found.', file=sys.stderr)
        sys.exit(73)
    styles = styles[:idx] + desktop_v2_css + '\n' + styles[idx:]
    changed = True

if changed:
    client_path.write_text(client, encoding='utf-8')
    styles_path.write_text(styles, encoding='utf-8')
    print('Applied indicator layout optimization for mobile and desktop.')
else:
    print('Indicator layout optimization already applied.')
