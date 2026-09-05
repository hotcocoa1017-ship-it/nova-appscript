from pathlib import Path

ready = (
    "function openMonthlyHousemanManageModal_" in Path('Client.html').read_text(encoding='utf-8')
    and "function cancelMonthlyManagedHousemanOrder" in Path('11_Monthly.js').read_text(encoding='utf-8')
    and "MONTHLY_HOUSEMAN_MANAGEMENT_V1 · 취소 오더는 현장 활성목록에서 제외" in Path('07_Houseman.js').read_text(encoding='utf-8')
)

if ready:
    print('MONTHLY_HOUSEMAN_MANAGEMENT_V1 already applied')
else:
    source = Path('scripts/patch_monthly_houseman_management_v1.py').read_text(encoding='utf-8')
    exec(compile(source, 'scripts/patch_monthly_houseman_management_v1.py', 'exec'), {'__name__': '__main__'})
