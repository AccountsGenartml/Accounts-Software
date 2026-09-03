"""
Genartml payroll engine.

Golden rule, enforced by assertion below:
    per_day = base_salary / working_days
    working_days is a MONTH CONSTANT, identical for every employee.
    It is never derived from attendance, days present, or payable days.
"""

import json
import calendar as _cal
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

CONFIG = Path(__file__).parent / "config"


def _d(x):
    return Decimal(str(x))


def money(x):
    return _d(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ConfigError(Exception):
    pass


class PayrollError(Exception):
    pass


# ---------------------------------------------------------------- calendar

class CompanyCalendar:
    def __init__(self, path=None):
        path = path or CONFIG / "calendar_2026.json"
        self.cfg = json.loads(Path(path).read_text())
        self.year = self.cfg["year"]
        wk = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        self.workdays = {wk[d] for d in self.cfg["work_week"]}
        self.holidays = {dt.date.fromisoformat(h["date"]): h["name"]
                         for h in self.cfg["public_holidays"]}
        for s in self.cfg.get("company_shutdown", []):
            a, b = dt.date.fromisoformat(s["from"]), dt.date.fromisoformat(s["to"])
            cur = a
            while cur <= b:
                self.holidays.setdefault(cur, s["name"])
                cur += dt.timedelta(days=1)

    def is_weekly_off(self, d):
        return d.weekday() not in self.workdays

    def month_days(self, year, month):
        return [dt.date(year, month, i)
                for i in range(1, _cal.monthrange(year, month)[1] + 1)]

    def breakdown(self, year, month):
        """Working days for the month. A holiday landing on a weekend is NOT
        subtracted twice -- Section C of the calendar grants no comp day."""
        days = self.month_days(year, month)
        weekly_offs = [d for d in days if self.is_weekly_off(d)]
        pub = [d for d in days if d in self.holidays and not self.is_weekly_off(d)]
        pub_on_weekend = [d for d in days if d in self.holidays and self.is_weekly_off(d)]
        working = len(days) - len(weekly_offs) - len(pub)
        return {
            "calendar_days": len(days),
            "weekly_offs": len(weekly_offs),
            "public_holidays": len(pub),
            "public_holidays_on_weekend": [
                {"date": d.isoformat(), "name": self.holidays[d]} for d in pub_on_weekend],
            "public_holiday_dates": [
                {"date": d.isoformat(), "name": self.holidays[d]} for d in pub],
            "working_days": working,
        }


# ---------------------------------------------------------------- rules

class Rules:
    def __init__(self, path=None):
        path = path or CONFIG / "rules.json"
        self.cfg = json.loads(Path(path).read_text())
        self.factors = self.cfg["pay_factors"]
        self.aliases = self.cfg.get("type_aliases", {})

    def normalise_type(self, raw):
        if raw is None:
            return None
        t = str(raw).strip()
        if t in self.factors:
            return t
        if t in self.aliases:
            return self.aliases[t]
        for k in self.factors:
            if k.lower() == t.lower():
                return k
        raise PayrollError(
            f"Unrecognised day type {t!r}. Add it to rules.json pay_factors or "
            f"type_aliases. Refusing to guess a pay factor.")

    def factor(self, t):
        return _d(self.factors[t]["factor"])

    def counts(self, t):
        return bool(self.factors[t]["counts_working_day"])

    def is_lop(self, t):
        return bool(self.factors[t].get("is_lop", False))

    def leave_bucket(self, t):
        return self.factors[t].get("leave_bucket")

    def professional_tax(self, gross):
        g = _d(gross)
        for slab in self.cfg["professional_tax_gujarat"]:
            if slab["upto"] is None or g <= _d(slab["upto"]):
                return _d(slab["tax"])
        return _d(0)

    def round_ot(self, hours):
        mode = self.cfg["overtime"].get("rounding", "none")
        h = _d(hours)
        if mode == "none":
            return h
        if mode == "floor_30min":
            return (h * 2).to_integral_value(rounding="ROUND_FLOOR") / 2
        raise ConfigError(f"Unknown OT rounding mode {mode!r}")


# ---------------------------------------------------------------- payroll

def compute_employee(emp, rows, working_days, rules, cal, year, month):
    """emp: dict with ctc_monthly, name, etc.  rows: list of normalised day rows."""
    ctc = _d(emp["ctc_monthly"])
    sp = rules.cfg["ctc_split"]
    ot_cfg = rules.cfg["overtime"]

    base_salary = ctc * _d(sp["base_pct"])
    incentive_full = ctc * _d(sp["incentive_pct"]) * _d(sp["incentive_default_payout"])
    allowance_full = ctc * _d(sp["allowance_pct"])

    # ---- THE divisor. Month constant. Never attendance-derived.
    wd = _d(working_days)
    if wd <= 0:
        raise PayrollError("working_days must be positive")
    per_day = base_salary / wd
    per_hour = per_day / _d(ot_cfg["paid_hours_per_day"])
    ot_rate = per_hour * _d(ot_cfg["multiplier"])

    rows_in_month = 0
    payable_days = _d(0)
    lop_days = _d(0)
    ot_hours = _d(0)
    leave_avail = {"CL": _d(0), "SL": _d(0), "EL": _d(0)}
    type_counts = {}
    flags = []

    month_dates = set(cal.month_days(year, month))
    seen = set()

    for r in rows:
        t = r["type"]
        d = r["date"]
        if d in seen:
            flags.append({"code": "DUPLICATE_DATE", "date": d.isoformat(),
                          "detail": "This date appears more than once in the timesheet."})
        seen.add(d)
        if d not in month_dates:
            flags.append({"code": "DATE_OUTSIDE_MONTH", "date": d.isoformat(),
                          "detail": "Row is not in the payroll month; ignored."})
            continue

        rows_in_month += 1
        type_counts[t] = type_counts.get(t, 0) + 1
        f = rules.factor(t)
        if rules.counts(t):
            payable_days += f
            if rules.is_lop(t):
                lop_days += 1
        bucket = rules.leave_bucket(t)
        if bucket:
            leave_avail[bucket] += 1

        ot = _d(r.get("approved_ot_hours") or 0)
        ot_hours += ot

        # ---- validation flags (surface, do not block)
        if ot > 0 and rules.is_lop(t):
            flags.append({"code": "OT_ON_UNPAID_DAY", "date": d.isoformat(),
                          "detail": f"{ot} h approved OT on a {t} day paid at 0% base."})
        if ot > 0 and r.get("check_in") is None and r.get("check_out") is None:
            flags.append({"code": "OT_WITHOUT_CLOCK_TRAIL", "date": d.isoformat(),
                          "detail": f"{ot} h approved OT with no check-in or check-out."})
        dev = r.get("device_ot_hours")
        if ot > 0 and dev is not None and ot > _d(dev) + _d("0.01"):
            flags.append({"code": "OT_EXCEEDS_DEVICE_LOG", "date": d.isoformat(),
                          "detail": f"Approved {ot} h vs device log {_d(dev)} h."})
        if not rules.counts(t) and (r.get("check_in") or r.get("check_out")) \
                and t not in ("OT Work (Weekend)", "Separate Working Day (counted as OT)"):
            flags.append({"code": "TYPE_CONTRADICTS_CLOCK", "date": d.isoformat(),
                          "detail": f"Clock times recorded on a {t} row."})
        if t in ("Office", "Client Office"):
            if r.get("check_in") is None or r.get("check_out") is None:
                flags.append({"code": "MISSING_PUNCH", "date": d.isoformat(),
                              "detail": f"{t} day missing a punch."})

    if payable_days > wd:
        flags.append({"code": "PAYABLE_EXCEEDS_WORKING",
                      "detail": f"payable_days {payable_days} > working_days {wd}. "
                                "Check for duplicate dates or a misclassified type."})

    ot_hours = Decimal(rules.round_ot(ot_hours)).quantize(Decimal("0.01"))

    # ---- mid-month join / exit
    frac = _d(1)
    active_wd = None
    join = emp.get("date_of_joining")
    exitd = emp.get("exit_date")
    if join or exitd:
        active = 0
        for d in cal.month_days(year, month):
            if cal.is_weekly_off(d) or (d in cal.holidays and not cal.is_weekly_off(d)):
                continue
            if join and d < join:
                continue
            if exitd and d > exitd:
                continue
            active += 1
        active_wd = active
        frac = _d(active) / wd if wd else _d(0)

    ep = rules.cfg["exit_policy"]
    allowance_paid = allowance_full * (frac if ep["prorate_allowance"] else _d(1))
    incentive_paid = incentive_full * (frac if ep["prorate_incentive"] else _d(1))

    base_earned = per_day * payable_days
    ot_payable = ot_rate * ot_hours
    gross = base_earned + ot_payable + allowance_paid + incentive_paid
    ptax = rules.professional_tax(gross)
    reimb = _d(emp.get("reimbursements") or 0)
    other_ded = _d(emp.get("other_deductions") or 0)
    total_ded = ptax + other_ded
    net = gross - total_ded + reimb

    if base_earned > 0 and ot_payable / base_earned > _d(rules.cfg["flags"]["ot_ratio_warn_pct"]):
        flags.append({"code": "OT_RATIO_HIGH",
                      "detail": f"OT is {(ot_payable / base_earned * 100):.0f}% of base earned."})

    # deduction-style presentation of the shortfall, for the payslip
    lop_deduction = per_day * lop_days
    partial_deduction = per_day * (wd - payable_days) - lop_deduction
    if partial_deduction < 0:
        partial_deduction = _d(0)

    return {
        "employee": emp,
        "rows_in_month": rows_in_month,
        "working_days": int(working_days),
        "active_working_days": active_wd,
        "month_fraction": frac,
        "payable_days": payable_days,
        "lop_days": lop_days,
        "type_counts": type_counts,
        "leave_availed": leave_avail,
        "base_salary": money(base_salary),
        "per_day": money(per_day),
        "per_hour": money(per_hour),
        "ot_rate": money(ot_rate),
        "ot_hours": ot_hours,
        "base_earned": money(base_earned),
        "ot_payable": money(ot_payable),
        "allowance_full": money(allowance_full),
        "incentive_full": money(incentive_full),
        "allowance_paid": money(allowance_paid),
        "incentive_paid": money(incentive_paid),
        "lop_deduction": money(lop_deduction),
        "partial_day_deduction": money(partial_deduction),
        "gross": money(gross),
        "professional_tax": money(ptax),
        "other_deductions": money(other_ded),
        "total_deductions": money(total_ded),
        "reimbursements": money(reimb),
        "net_pay": money(net),
        "flags": flags,
    }


def run_payroll(employees_rows, working_days, rules, cal, year, month):
    results = [compute_employee(e, rows, working_days, rules, cal, year, month)
               for e, rows in employees_rows]
    # No timesheet data for the month means we have nothing to pay against.
    # Without this guard the fixed allowance and incentive would still pay out.
    blank = [r["employee"]["name"] for r in results if r["rows_in_month"] == 0]
    if blank:
        raise PayrollError(
            "NO_TIMESHEET_DATA: this workbook has no rows for the selected month for "
            + ", ".join(blank)
            + ". Check you picked the right month and the right workbook. "
              "Refusing to pay allowance and incentive against an empty timesheet.")

    # HARD ASSERTION -- the bug this engine exists to prevent
    divisors = {r["working_days"] for r in results}
    if len(divisors) > 1:
        raise PayrollError(
            f"WORKING_DAYS_MISMATCH: employees in one run got different divisors "
            f"{sorted(divisors)}. working_days must be a month constant. Halting.")
    return results
