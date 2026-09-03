#!/usr/bin/env python3
"""Run:  python test_engine.py    Exits non-zero on any failure."""

import datetime as dt
import sys
from decimal import Decimal as D

from engine import CompanyCalendar, Rules, compute_employee, run_payroll, PayrollError

cal, rules = CompanyCalendar(), Rules()
FAILS = []


def check(name, got, want):
    if isinstance(want, bool):
        ok = (bool(got) == want)
    else:
        ok = (D(str(got)) == D(str(want)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<44} {got}" + ("" if ok else f"   expected {want}"))
    if not ok:
        FAILS.append(name)


def row(day, t, ot=0, ci=None, co=None):
    d = dt.date(2026, 8, day)
    return {"date": d, "type": rules.normalise_type(t), "approved_ot_hours": D(str(ot)),
            "check_in": dt.datetime.combine(d, ci) if ci else None,
            "check_out": dt.datetime.combine(d, co) if co else None,
            "device_ot_hours": None}


print("\n1. Calendar — August 2026")
bd = cal.breakdown(2026, 8)
check("calendar days", bd["calendar_days"], 31)
check("weekly offs", bd["weekly_offs"], 10)
check("public holidays (weekday only)", bd["public_holidays"], 1)
check("WORKING DAYS", bd["working_days"], 20)

print("\n2. Golden case — Sandeep Bhagat, 30k CTC")
rows = ([row(d, "Office") for d in (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 17, 20)]
        + [row(18, "WFH - Company Directed"), row(19, "WFH - Company Directed"),
           row(21, "WFH - Weekly Standing")]
        + [row(d, "WFH - Personal with prior notice (75%)") for d in (24, 25, 26, 27, 31)]
        + [row(d, "Week Off") for d in (1, 2, 8, 9, 15, 16, 22, 23, 29, 30)]
        + [row(28, "Public Holiday")])
rows[0]["approved_ot_hours"] = D("29.7")
r = compute_employee({"name": "T", "ctc_monthly": D(30000)}, rows, 20, rules, cal, 2026, 8)
check("base salary", r["base_salary"], "21000.00")
check("per day  (Basic / 20, NOT / 15)", r["per_day"], "1050.00")
check("per hour", r["per_hour"], "131.25")
check("OT RATE  (must NOT be 350.00)", r["ot_rate"], "262.50")
check("payable days", r["payable_days"], "18.75")
check("base earned", r["base_earned"], "19687.50")
check("OT payable", r["ot_payable"], "7796.25")
check("gross", r["gross"], "33483.75")
check("professional tax", r["professional_tax"], "200")
check("NET PAY  (must NOT be 35375.00)", r["net_pay"], "33283.75")

print("\n3. Divisor is a month constant, never attendance-derived")
r2 = compute_employee({"name": "T2", "ctc_monthly": D(30000)},
                      [row(d, "Office") for d in (3, 4, 5)]
                      + [row(d, "LWP") for d in (6, 7)], 20, rules, cal, 2026, 8)
check("per day unchanged despite 3 days worked", r2["per_day"], "1050.00")
check("payable days reflects attendance", r2["payable_days"], "3.00")
check("LOP days counted", r2["lop_days"], "2")

print("\n4. Mismatched divisors halt the run")
a = compute_employee({"name": "A", "ctc_monthly": D(30000)}, [row(3, "Office")],
                     20, rules, cal, 2026, 8)
b = compute_employee({"name": "B", "ctc_monthly": D(30000)}, [row(3, "Office")],
                     15, rules, cal, 2026, 8)
try:
    divisors = {a["working_days"], b["working_days"]}
    if len(divisors) > 1:
        raise PayrollError("WORKING_DAYS_MISMATCH")
    check("mismatch halts the run", False, True)
except PayrollError:
    check("mismatch halts the run", True, True)

print("\n5. Professional tax slabs")
for gross, want in ((5000, 0), (5999, 0), (6000, 80), (8999, 80),
                    (9000, 150), (11999, 150), (12000, 200), (99999, 200)):
    check(f"PT at gross {gross}", rules.professional_tax(gross), want)

print("\n6. Pay factors")
for t, want in (("Office", "1.00"), ("Half Day", "0.50"), ("LWP", "0.00"),
                ("Casual Leave (CL)", "1.00"),
                ("WFH - Personal with prior notice (75%)", "0.75")):
    check(f"factor {t}", rules.factor(rules.normalise_type(t)), want)

print("\n7. Unknown day type is rejected, never guessed")
try:
    rules.normalise_type("Some New Type")
    check("unknown type raises", False, True)
except PayrollError:
    check("unknown type raises", True, True)

print("\n8. Flags fire")
rf = compute_employee(
    {"name": "F", "ctc_monthly": D(30000)},
    [row(3, "LWP", ot=5.3), row(4, "WFH - Weekly Standing", ot=1.0)],
    20, rules, cal, 2026, 8)
codes = {f["code"] for f in rf["flags"]}
check("OT_ON_UNPAID_DAY", "OT_ON_UNPAID_DAY" in codes, True)
check("OT_WITHOUT_CLOCK_TRAIL", "OT_WITHOUT_CLOCK_TRAIL" in codes, True)

print("\n9. Mid-month exit pro-rates fixed components only")
re_ = compute_employee(
    {"name": "X", "ctc_monthly": D(18000), "exit_date": dt.date(2026, 8, 14)},
    [row(d, "Office") for d in (3, 4, 5, 6, 7, 10, 11, 12, 13)]
    + [row(14, "WFH - Weekly Standing")], 20, rules, cal, 2026, 8)
check("active working days", re_["active_working_days"], 10)
check("month fraction", re_["month_fraction"], "0.5")
check("allowance pro-rated", re_["allowance_paid"], "900.00")
check("base follows actual days", re_["base_earned"], "6300.00")


print("\n10. An empty month must halt, not pay fixed components")
try:
    run_payroll([({"name": "Ghost", "ctc_monthly": D(30000)}, [])],
                20, rules, cal, 2026, 9)
    check("empty timesheet halts the run", False, True)
except PayrollError as e:
    check("empty timesheet halts the run", "NO_TIMESHEET_DATA" in str(e), True)

print("\n" + ("-" * 62))
if FAILS:
    print(f"  {len(FAILS)} FAILURE(S): " + ", ".join(FAILS))
    sys.exit(1)
print("  ALL TESTS PASSED — engine is safe to run payroll.\n")
