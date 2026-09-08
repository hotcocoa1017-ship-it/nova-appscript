from pathlib import Path

CLIENT = Path('Client.html')
MARKER = 'INDICATOR_HOUSEMAN_ORDER_UI_V1'


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly 1 anchor, found {count}')
    return text.replace(old, new, 1)


text = CLIENT.read_text(encoding='utf-8')
if MARKER in text:
    print(f'{MARKER}: already applied')
    raise SystemExit(0)

css = r'''
  /* INDICATOR_HOUSEMAN_ORDER_UI_V1 */
  .indicator-summary-filter {
    appearance: none;
    color: inherit;
    cursor: pointer;
    transition: background .15s ease, color .15s ease, border-color .15s ease, box-shadow .15s ease;
  }
  .indicator-summary-filter:hover {
    border-color: #9ca3af;
    background: #f8fafc;
  }
  .indicator-summary-filter.active {
    border-color: #111827;
    background: #111827;
    color: #fff;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .16);
  }
  .indicator-summary-filter:focus-visible {
    outline: 2px solid #2563eb;
    outline-offset: 2px;
  }
'''
text = replace_once(
    text,
    '</style>\n<script>',
    css + '\n</style>\n<script>',
    'Client style/script boundary'
)

helpers = r'''
  function indicatorIsPendingHousemanOrder_(order) { // (미완료 하우스맨 오더 판정)
    return !['COMPLETED', 'UNABLE'].includes(String(order?.statusCode || '').trim().toUpperCase());
  }

  function indicatorRoomPendingOrderTooltip_(room) { // (객실카드 숫자뱃지 hover에 실제 오더내용 표시)
    const roomNo = String(room?.roomNo || '').trim();
    if (!roomNo) return '';
    const pending = (state.indicator.data?.orders || [])
      .filter(order => String(order?.roomNo || '').trim() === roomNo && indicatorIsPendingHousemanOrder_(order));
    if (!pending.length) return '';
    return pending.map(order => {
      const item = String(order?.itemSummary || '').trim();
      const note = String(order?.note || '').trim();
      if (item && note && note !== item) return `${item} · ${note}`;
      return item || note || '오더내용 없음';
    }).join('\n');
  }

  function indicatorOrderListFilter_() { // (오더 처리현황 필터 기본값)
    const value = String(state.indicator.orderListFilter || 'ALL').trim().toUpperCase();
    return ['ROOM', 'PENDING', 'ALL'].includes(value) ? value : 'ALL';
  }

  function indicatorOrderMatchesListFilter_(order, filter) { // (처리현황 필터 판정)
    if (filter === 'PENDING') return indicatorIsPendingHousemanOrder_(order);
    if (filter === 'ROOM') {
      const roomNo = String(order?.roomNo || '').trim();
      return Boolean(roomNo && roomNo !== '공용');
    }
    return true;
  }

  function indicatorOrderListEmptyMessage_(filter) { // (필터별 빈 목록 안내)
    if (filter === 'PENDING') return '미완료 하우스맨 오더가 없습니다.';
    if (filter === 'ROOM') return '객실 하우스맨 오더가 없습니다.';
    return '등록된 하우스맨 오더가 없습니다.';
  }

'''
text = replace_once(
    text,
    '  function renderIndicatorSummary() { // (통합 화면 요약)\n',
    helpers + '  function renderIndicatorSummary() { // (통합 화면 요약)\n',
    'renderIndicatorSummary function anchor'
)

old_summary = r'''    $('indicatorSummary').innerHTML = `
      <span class="summary-pill">객실 ${rooms.length}</span>
      <span class="summary-pill">미완료 오더 ${activeOrders}</span>
      <span class="summary-pill">전체 오더 ${orders.length}</span>`;
'''
new_summary = r'''    const orderListFilter = indicatorOrderListFilter_();
    $('indicatorSummary').innerHTML = `
      <button type="button" class="summary-pill indicator-summary-filter${orderListFilter === 'ROOM' ? ' active' : ''}" data-order-list-filter="ROOM" aria-pressed="${orderListFilter === 'ROOM'}" title="객실번호가 있는 오더만 보기">객실 ${rooms.length}</button>
      <button type="button" class="summary-pill indicator-summary-filter${orderListFilter === 'PENDING' ? ' active' : ''}" data-order-list-filter="PENDING" aria-pressed="${orderListFilter === 'PENDING'}" title="미완료 오더만 보기">미완료 오더 ${activeOrders}</button>
      <button type="button" class="summary-pill indicator-summary-filter${orderListFilter === 'ALL' ? ' active' : ''}" data-order-list-filter="ALL" aria-pressed="${orderListFilter === 'ALL'}" title="전체 오더 보기">전체 오더 ${orders.length}</button>`;
    $('indicatorSummary').querySelectorAll('[data-order-list-filter]').forEach(button => {
      button.addEventListener('click', () => {
        state.indicator.orderListFilter = String(button.dataset.orderListFilter || 'ALL').toUpperCase();
        renderIndicatorSummary();
        renderOrderList();
      });
    });
'''
text = replace_once(text, old_summary, new_summary, 'indicator summary pills')

old_list = r'''    const scrollTop = container.scrollTop;
    const orders = [...(state.indicator.data?.orders || [])].sort((a, b) =>
'''
new_list = r'''    const scrollTop = container.scrollTop;
    const orderListFilter = indicatorOrderListFilter_();
    const orders = (state.indicator.data?.orders || [])
      .filter(order => indicatorOrderMatchesListFilter_(order, orderListFilter))
      .slice()
      .sort((a, b) =>
'''
text = replace_once(text, old_list, new_list, 'order list source/filter')

old_empty = "      container.innerHTML = '<div class=\"empty-order\">등록된 하우스맨 오더가 없습니다.</div>';\n"
new_empty = "      container.innerHTML = `<div class=\"empty-order\">${escapeHtml(indicatorOrderListEmptyMessage_(orderListFilter))}</div>`;\n"
text = replace_once(text, old_empty, new_empty, 'order list empty state')

old_badge = r'''        ${room.pendingOrderCount ? `<span class="room-order-count" title="미완료 하우스맨 오더">${room.pendingOrderCount}</span>` : ''}
'''
new_badge = r'''        ${room.pendingOrderCount ? `<span class="room-order-count" title="${escapeAttr(indicatorRoomPendingOrderTooltip_(room))}" aria-label="${escapeAttr(indicatorRoomPendingOrderTooltip_(room))}">${room.pendingOrderCount}</span>` : ''}
'''
text = replace_once(text, old_badge, new_badge, 'room pending-order badge tooltip')

CLIENT.write_text(text, encoding='utf-8')
print(f'{MARKER}: applied')
