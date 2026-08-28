from pathlib import Path
import subprocess

PATH = Path('cloudrun/index.js')
text = PATH.read_text(encoding='utf-8')

marker = "app.post(\n  '/v1/houseman-orders',"
if text.count(marker) != 1:
    raise SystemExit(f'PATCH_ERROR: houseman POST marker expected 1 match, found {text.count(marker)}')

block = r'''/**
 * HOUSEMAN 모바일용 PostgreSQL 직접 조회.
 * 배정/공동전달 반영을 Sheet 미러와 분리해 5초 미만 자동반영 경로로 사용한다.
 */
app.get(
  '/v1/houseman-orders',
  async (req, res, next) => {
    let client;
    try {
      client = await pool.connect();
      const auth = authBearer(req);
      const user = await loadUser(client, auth.employeeNo);

      if (String(user.role || '').toUpperCase() !== 'HOUSEMAN') {
        throw httpError(403, 'FORBIDDEN', '하우스맨 오더 조회 권한이 없습니다.');
      }

      const businessDate = cleanText_(req.query.businessDate, 20);
      const site = cleanText_(req.query.site || user.default_site, 80);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(businessDate)) {
        throw httpError(400, 'INVALID_REQUEST', '업무일자가 필요합니다.');
      }
      if (!site) {
        throw httpError(400, 'INVALID_REQUEST', '사업장이 필요합니다.');
      }
      if (!allowedForSite(user, site)) {
        throw httpError(403, 'FORBIDDEN', '해당 사업장 조회 권한이 없습니다.');
      }

      const employeeNo = String(user.employee_no || '');
      const { rows } = await client.query(
        `select *
           from public.nova_houseman_orders
          where business_date=$1::date
            and site=$2
            and (
              assigned_employee_no=$3
              or processor_employee_no=$3
              or (
                route_locked is false
                and $3 = any(coalesce(route_candidate_employee_nos, '{}'::text[]))
              )
            )
          order by updated_at desc, order_id desc`,
        [businessDate, site, employeeNo]
      );

      res.json({
        ok: true,
        businessDate,
        site,
        orders: rows.map(housemanOrderDto_),
        serverTime: new Date().toISOString()
      });
    } catch (e) {
      next(e);
    } finally {
      if (client) client.release();
    }
  }
);

'''

text = text.replace(marker, block + marker, 1)
PATH.write_text(text, encoding='utf-8')

check = PATH.read_text(encoding='utf-8')
required = [
    "app.get(\n  '/v1/houseman-orders'",
    "assigned_employee_no=$3",
    "route_locked is false",
    "rows.map(housemanOrderDto_)",
]
for item in required:
    if item not in check:
        raise SystemExit(f'PATCH_ERROR: missing marker: {item}')

subprocess.run(['node', '--check', str(PATH)], check=True)
print('HOUSEMAN_MOBILE_DB_READ_V74_OK')
print('Changed: cloudrun/index.js only')
print('HOUSEMAN mobile DB list endpoint: authenticated + site scoped + assignment/candidate visibility')
