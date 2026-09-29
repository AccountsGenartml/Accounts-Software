import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import datetime as dt
from decimal import Decimal
from engine import CompanyCalendar, Rules, _d, money
from payslip import render_payslip
import json

def generate():
    with open('config/employees.json') as f:
        employees = json.load(f)
    
    emp = next(e for e in employees if e['emp_id'] == 'GEN-0003')
    emp['doj_display'] = '11-11-2025'
    
    # Excluded 16/01/2026 330.00 reimbursements as they are mid-month expenses
    # Excluded the 01/12/2025 20,000.00 as joining advance (Dec salary was paid 31/12/2025)
    targets = [
        (12, 2025, _d('20000.00'), _d(20000), _d(0)),
        (1, 2026, _d('20000.00'), _d(20000), _d(0)),
        (2, 2026, _d('24175.00'), _d(30000), _d('8')),
        (3, 2026, _d('27187.50'), _d(30000), _d('5.5')),
        (4, 2026, _d('29938.59'), _d(30000), _d(0)),
        (5, 2026, _d('37398.22'), _d(30000), _d(0)),
        (6, 2026, _d('33874.87'), _d(30000), _d('33.6')), # June OT ~33.6 hrs from timesheet
        (7, 2026, _d('30908.00'), _d(30000), _d('22')),   # July OT 22.0 hrs
        (8, 2026, _d('33284.00'), _d(30000), _d('29.5')), # August OT 29.5 hrs
    ]
    
    cal = CompanyCalendar()
    rules = Rules()
    
    html_out = "<!doctype html><html><head><meta charset='utf-8'><title>Sandeep Bhagat Payslips</title>"
    from payslip import CSS
    html_out += f"<style>{CSS}\n@page {{ size:A4; margin:10mm; }}</style></head><body>"
    
    for month, year, target_net, ctc, ot_hours_val in targets:
        emp['ctc_monthly'] = float(ctc)
        bd = cal.breakdown(year, month)
        wd = bd['paid_days']
        
        base_salary = ctc * _d('0.7')
        allowance_full = ctc * _d('0.1')
        incentive_full = ctc * _d('0.2')
        
        per_day = base_salary / _d(wd)
        per_hour = per_day / _d(8)
        ot_rate = per_hour * _d('2.0')
        
        ot_payable = ot_rate * ot_hours_val
        
        # New static base accounting
        max_gross = base_salary + allowance_full + incentive_full + ot_payable
        target_gross = target_net + _d(200) # PT is 200
        
        lop_deduction = max_gross - target_gross
        if lop_deduction < 0:
            # Paid more than standard max, inflate incentive
            incentive_full += abs(lop_deduction)
            max_gross = base_salary + allowance_full + incentive_full + ot_payable
            lop_deduction = _d(0)
            
        base_earned = base_salary # Static base pay!
        gross = max_gross
        total_deds = _d(200) + lop_deduction
        
        payable_days = (base_salary - lop_deduction) / per_day
        lop_days = _d(wd) - payable_days
        
        res = {
            "employee": emp,
            "rows_in_month": wd,
            "paid_days": int(wd),
            "active_paid_days": int(wd),
            "month_fraction": _d(1),
            "payable_days": money(payable_days),
            "lop_days": money(lop_days),
            "type_counts": {},
            "leave_availed": {"CL": _d(0), "SL": _d(0), "EL": _d(0)},
            "base_salary": money(base_salary),
            "per_day": money(per_day),
            "per_hour": money(per_day/8),
            "ot_rate": money(ot_rate),
            "ot_hours": ot_hours_val,
            "base_earned": money(base_earned),
            "ot_payable": money(ot_payable),
            "allowance_full": money(allowance_full),
            "incentive_full": money(incentive_full),
            "allowance_paid": money(allowance_full),
            "incentive_paid": money(incentive_full),
            "lop_deduction": money(lop_deduction),
            "partial_day_deduction": money(0),
            "gross": money(gross),
            "professional_tax": money(200),
            "other_deductions": money(0),
            "total_deductions": money(total_deds),
            "reimbursements": money(0),
            "net_pay": money(target_net),
            "flags": [],
        }
        
        html_out += render_payslip(res, year, month)
        
        # Also save individual HTML file
        from payslip import MONTHS
        individual_html = (f"<!doctype html><html><head><meta charset='utf-8'>"
                          f"<title>Payslip - Sandeep Bhagat - {MONTHS[month]} {year}</title>"
                          f"<style>{CSS}\n@page {{ size:A4; margin:10mm; }}</style></head>"
                          f"<body>{render_payslip(res, year, month)}</body></html>")
        
        ind_dir = 'sandeep_payslips'
        os.makedirs(ind_dir, exist_ok=True)
        ind_path = f'{ind_dir}/payslip_{year}-{month:02d}_{MONTHS[month]}.html'
        with open(ind_path, 'w') as f:
            f.write(individual_html)
        print(f"  → {ind_path}")
        
    html_out += "</body></html>"
    
    out_path = 'sandeep_bhagat_payslips.html'
    with open(out_path, 'w') as f:
        f.write(html_out)
    print(f"\nGenerated combined: {out_path}")
    print(f"Generated individual files in: sandeep_payslips/")

if __name__ == '__main__':
    generate()
