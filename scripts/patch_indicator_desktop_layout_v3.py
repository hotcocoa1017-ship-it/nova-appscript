from pathlib import Path
import sys

MARKER = 'INDICATOR_DESKTOP_LAYOUT_V3'
styles_path = Path('Styles.html')
styles = styles_path.read_text(encoding='utf-8')

if MARKER in styles:
    print('Indicator desktop layout V3 already applied.')
    raise SystemExit(0)

css = r'''

  /* INDICATOR_DESKTOP_LAYOUT_V3
   * 데스크탑 상단 한 줄: 업무일자 · 사업장 · 조회하기 · 검색 · (가변 여백) · 객실현황 업로드.
   * 객실현황 업로드는 화면 우측 끝에 고정하고 모바일 레이아웃은 변경하지 않습니다.
   */
  @media (min-width: 761px) {
    .indicator-page .indicator-controls {
      grid-template-columns: 220px 220px 104px minmax(220px, 320px) minmax(0, 1fr) 160px;
      column-gap: 10px;
      align-items: end;
    }

    .indicator-page #roomUploadButton {
      grid-column: 6;
      grid-row: 1;
      justify-self: end;
      align-self: end;
      width: 160px;
      min-width: 160px;
      max-width: 160px;
      height: 40px;
      min-height: 40px;
      margin: 0;
      padding: 0 14px;
      border-radius: 9px;
      font-size: 13px;
      white-space: nowrap;
    }

    .indicator-page #indicatorSummary {
      grid-column: 1 / -1;
    }
  }
'''

idx = styles.rfind('</style>')
if idx < 0:
    print('ERROR: Styles.html closing </style> not found.', file=sys.stderr)
    raise SystemExit(74)

styles = styles[:idx] + css + '\n' + styles[idx:]
styles_path.write_text(styles, encoding='utf-8')
print('Applied indicator desktop layout V3.')
