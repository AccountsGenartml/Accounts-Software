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
    
    emp = next(e for e in employees if e['emp_id'] == 'GEN-0006')
    emp['doj_display'] = '05-01-2026'
    ctc = _d(25000)
    
    targets = [
        (2, 2026, _d('18200.00'), _d(20000), _d(0)),
        (3, 2026, _d('18075.00'), _d(20000), _d('2.5')),
        (4, 2026, _d('19144.32'), _d(20000), _d(0)),
        (5, 2026, _d('18130.81'), _d(25000), _d(0)),
        (6, 2026, _d('18748.31'), _d(25000), _d(6)),
        (7, 2026, _d('23060.00'), _d(25000), _d(4)),
        (8, 2026, _d('27346.56'), _d(25000), _d(23)),
    ]
    
    cal = CompanyCalendar()
    rules = Rules()
    
    html_out = "<!doctype html><html><head><meta charset='utf-8'><title>Prashant Songara Payslips</title>"
    from payslip import CSS
    html_out += f"<style>{CSS}\\n@page {{ size:A4; margin:10mm; }}</style></head><body>"
    
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
                          f"<title>Payslip - Prashant Songara - {MONTHS[month]} {year}</title>"
                          f"<style>{CSS}\n@page {{ size:A4; margin:10mm; }}</style></head>"
                          f"<body>{render_payslip(res, year, month)}</body></html>")
        
        ind_dir = 'prashant_payslips'
        os.makedirs(ind_dir, exist_ok=True)
        ind_path = f'{ind_dir}/payslip_{year}-{month:02d}_{MONTHS[month]}.html'
        with open(ind_path, 'w') as f:
            f.write(individual_html)
        print(f"  → {ind_path}")
        
    html_out += "</body></html>"
    
    out_path = 'prashant_songara_payslips.html'
    with open(out_path, 'w') as f:
        f.write(html_out)
    print(f"\nGenerated combined: {out_path}")
    print(f"Generated individual files in: prashant_payslips/")
    
    # Convert each individual HTML to PDF using macOS built-in tools
    print("\nConverting to PDF using macOS print system...")
    import subprocess
    for month, year, _, _, _ in targets:
        from payslip import MONTHS
        html_file = os.path.abspath(f'prashant_payslips/payslip_{year}-{month:02d}_{MONTHS[month]}.html')
        pdf_file = os.path.abspath(f'prashant_payslips/payslip_{year}-{month:02d}_{MONTHS[month]}.pdf')
        
        # Use /usr/sbin/cupsfilter or textutil won't work for HTML with CSS
        # Instead use osascript to open in Safari and print to PDF
        script = f'''
        tell application "Safari"
            open location "file://{html_file}"
            delay 2
        end tell
        do shell script "/usr/bin/python3 -c \\"import subprocess; subprocess.run(['lp', '-d', 'Save_as_PDF', '{html_file}'])\\""
        '''
        # Simpler approach: just notify user
        print(f"  → {pdf_file} (open HTML in browser, Cmd+P → Save as PDF)")

if __name__ == '__main__':
    generate()
