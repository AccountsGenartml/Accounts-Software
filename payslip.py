"""Renders payslips as HTML (and PDF if a renderer is available).

Logo priority:
    1.  assets/company_logo.png   — drop YOUR company logo here
    2.  assets/logo_mark_black.png — the default Genartml wordmark
"""

import base64
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"

import json

def get_branding():
    try:
        p = Path(__file__).parent / "config" / "branding.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except:
        pass
    return {
        "company_name": "GENARTML PVT. LTD.",
        "cin": "U74909GJ2025PTC168491",
        "epf": "N/A",
        "location": "Ahmedabad, Gujarat",
        "theme_color": "#18181b",
        "theme_text_color": "#f4f4f5",
        "footer_text": "This is a system-generated payslip and does not require a signature.",
        "show_leave_balance": True
    }

MONTHS = ["", "January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


def _logo():
    """Return a base-64 data-URI for the company logo.
    Checks for a user-supplied file first, then the default."""
    for name in ("company_logo.png", "company_logo.jpg", "company_logo.svg",
                 "logo.png", "logo.jpg",
                 "logo_mark_black.png", "logo_wordmark.png"):
        p = ASSETS / name
        if p.exists():
            ext = p.suffix.lstrip(".")
            mime = {"png": "image/png", "jpg": "image/jpeg",
                    "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, "image/png")
            return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()
    return ""


def _r(x):
    """Format a number as ₹ with two decimals."""
    return f"₹{x:,.2f}"


def _words(n):
    """Convert a number to Indian-English words for cheque writing."""
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
            "sixteen", "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
            "eighty", "ninety"]

    def two(x):
        if x < 20:
            return ones[x]
        return tens[x // 10] + ("-" + ones[x % 10] if x % 10 else "")

    def three(x):
        if x < 100:
            return two(x)
        return ones[x // 100] + " hundred" + (" " + two(x % 100) if x % 100 else "")

    rupees = int(n)
    paisa = int(round((float(n) - rupees) * 100))
    parts = []
    for div, label in ((10000000, "crore"), (100000, "lakh"), (1000, "thousand")):
        if rupees >= div:
            parts.append(three(rupees // div) + " " + label)
            rupees %= div
    if rupees:
        parts.append(three(rupees))
    s = " ".join(parts) if parts else "zero"
    s = s[0].upper() + s[1:]
    if paisa:
        return f"{s} rupees and {two(paisa)} paisa only."
    return f"{s} rupees only."


def generate_css(branding):
    theme_color = branding.get("theme_color", "#18181b")
    text_color = branding.get("theme_text_color", "#f4f4f5")
    
    return f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

*{{box-sizing:border-box;margin:0;padding:0}}
html{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
body{{font-family:'Inter','Segoe UI',Helvetica,Arial,sans-serif;
     color:#1a1a1a;background:#fff;font-size:9.2px;line-height:1.45}}

.page{{
  width:100%;max-width:194mm;margin:0 auto;
  padding:22px 26px 14px;
  page-break-after:always;page-break-inside:avoid;
}}
.page:last-child{{page-break-after:auto}}

.hdr{{
  display:flex;justify-content:space-between;align-items:flex-start;
  border-bottom:2px solid {theme_color};padding-bottom:12px;margin-bottom:0;
}}
.brand{{display:flex;align-items:center;gap:12px}}
.brand img{{height:28px;width:auto;object-fit:contain}}
.brand-name{{font-size:15px;font-weight:800;letter-spacing:.2px;color:#18181b}}
.cin{{color:#71717a;font-size:7.5px;margin-top:3px;letter-spacing:.15px}}
.for-box{{text-align:right}}
.for-label{{color:#71717a;font-size:8.5px;text-transform:uppercase;
           letter-spacing:1.4px;font-weight:500}}
.for-month{{font-size:14px;font-weight:700;margin-top:2px;color:#18181b}}

.banner{{
  background:{theme_color};color:{text_color};text-align:center;
  padding:8px 16px;font-weight:700;letter-spacing:2.5px;
  font-size:9.8px;margin:16px 0 14px;text-transform:uppercase;
  border-radius:4px;
}}

.meta{{width:100%;border-collapse:collapse;margin-bottom:14px;
      border-radius:6px;overflow:hidden;box-shadow:0 0 0 1px #e4e4e7;}}
.meta td{{
  padding:6px 10px;border:1px solid #e4e4e7;font-size:9px;
  vertical-align:top;
}}
.meta .k{{color:#52525b;width:102px;font-weight:400;background:#fafafa}}
.meta .v{{font-weight:600;color:#18181b}}

.cols{{display:flex;gap:12px;margin-bottom:12px}}
.cols>div{{flex:1;min-width:0}}

.sec{{width:100%;border-collapse:collapse;border-radius:6px;
     overflow:hidden;box-shadow:0 0 0 1px #e4e4e7;}}
.sec th{{
  background:#f4f4f5;text-align:left;padding:6.5px 10px;
  font-size:7.8px;letter-spacing:1px;font-weight:700;
  color:#3f3f46;border:1px solid #e4e4e7;text-transform:uppercase;
}}
.sec th.n{{text-align:right}}
.sec td{{padding:5.5px 10px;border:1px solid #f4f4f5;font-size:9px}}
.sec td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.sec tr.tot td{{
  background:#f4f4f5;font-weight:700;
  border-top:1.5px solid #d4d4d8;
}}
.muted{{color:#a1a1aa}}

.net{{
  background:{theme_color};color:{text_color};display:flex;
  justify-content:space-between;align-items:center;
  padding:14px 22px;margin-top:14px;border-radius:6px;
}}
.net .lbl{{font-weight:700;font-size:12px;letter-spacing:.2px}}
.net .sub{{color:rgba(255,255,255,0.7);font-size:8.5px;margin-top:3px}}
.net .amt{{font-size:24px;font-weight:800;letter-spacing:-.6px}}

.words{{
  font-style:italic;color:#52525b;font-size:8.8px;
  margin:10px 0 14px;line-height:1.5;
}}

.leave{{width:100%;border-collapse:collapse;margin-bottom:12px;
       border-radius:6px;overflow:hidden;box-shadow:0 0 0 1px #e4e4e7;}}
.leave th{{
  background:#f4f4f5;text-align:left;padding:6px 10px;
  font-size:7.8px;letter-spacing:1px;font-weight:700;
  color:#3f3f46;border:1px solid #e4e4e7;text-transform:uppercase;
}}
.leave th.n{{text-align:right}}
.leave td{{padding:5.5px 10px;border:1px solid #f4f4f5;font-size:9px}}
.leave td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.leave td b{{font-weight:700}}

.flags{{
  margin:12px 0 10px;border:1px solid #fcd34d;background:#fffbeb;
  padding:10px 14px;border-radius:6px;
}}
.flags h4{{margin:0 0 6px;font-size:9.5px;letter-spacing:1.2px;
          color:#b45309;text-transform:uppercase}}
.flags li{{font-size:7.8px;color:#78350f;margin-bottom:2px}}

.foot{{
  display:flex;justify-content:space-between;color:#71717a;
  font-size:7.8px;margin-top:12px;border-top:1px solid #f4f4f5;
  padding-top:8px;
}}
.center{{
  text-align:center;color:#a1a1aa;font-size:7.8px;
  margin-top:6px;font-style:italic;
}}

@media print{{
  .page{{padding:0}}
  body{{background:transparent}}
  .meta, .sec, .leave {{ box-shadow:none; border: 1px solid #e4e4e7; }}
}}
"""

def _meta_rows(res, year, month, branding):
    """Build the 6-row employee details table."""
    e = res["employee"]
    pd_ = res["payable_days"]
    left = [
        ("Employee Name", e.get("name", "")),
        ("Designation", e.get("designation") or "N/A"),
        ("Date of Joining", e.get("doj_display") or "N/A"),
        ("PAN", e.get("pan") or "N/A"),
        ("Bank Name", e.get("bank_name") or "N/A"),
        ("Payable Days", f"{pd_:g} / {res['paid_days']}"),
    ]
    right = [
        ("Employee ID", e.get("emp_id") or "N/A"),
        ("Department", e.get("department") or "N/A"),
        ("UAN", e.get("uan") or "N/A"),
        ("Bank A/C No.", e.get("bank_ac") or "N/A"),
        ("IFSC", e.get("ifsc") or "N/A"),
        ("LWP Days", f"{res['lop_days']:g}"),
    ]
    out = ""
    for (lk, lv), (rk, rv) in zip(left, right):
        out += (f"<tr><td class='k'>{lk}</td><td class='v'>{lv}</td>"
                f"<td class='k'>{rk}</td><td class='v'>{rv}</td></tr>")
    return out


def render_payslip(res, year, month):
    """Generate the complete HTML for one employee's payslip."""
    e = res["employee"]
    branding = get_branding()

    # ── Earnings ──
    earn = [("Basic Salary", res["base_earned"]),
            ("House Rent Allowance", None),
            ("Variable Incentive", res["incentive_paid"]),
            ("Performance Bonus", res.get("performance_bonus", Decimal(0))),
            ("Fixed Allowance", res["allowance_paid"]),
            ("Overtime Allowance", res["ot_payable"]),
            ("Reimbursements", res.get("reimbursements", Decimal(0)))]

    # ── Deductions ──
    ded = [("Provident Fund (EPF)", res.get("epf") or None),
           ("Employees' State Insurance (ESI)", res.get("esi") or None),
           ("Professional Tax", res["professional_tax"]),
           ("TDS (Income Tax)", res.get("tds") or None),
           ("Loan / Advance Recovery", None),
           ("Leave Without Pay (LWP)", res["lop_deduction"] or None),
           ("Other Deductions", res["other_deductions"] or None)]

    def rows(items):
        h = ""
        for k, v in items:
            cell = _r(v) if v else "<span class='muted'>N/A</span>"
            h += f"<tr><td>{k}</td><td class='n'>{cell}</td></tr>"
        return h

    ded_total = res["total_deductions"]

    # ── Flags ──
    flags_html = ""
    if res["flags"]:
        items = "".join(
            f"<li><b>{f['code']}</b>{' &middot; ' + f['date'] if f.get('date') else ''} — {f['detail']}</li>"
            for f in res["flags"])
        flags_html = ("<div class='flags'><h4>Review Before Release</h4>"
                      f"<ul style='margin:0;padding-left:16px'>{items}</ul></div>")

    # ── Leave balance ──
    lv = res["leave_availed"]
    op = e.get("leave_opening", {}) or {}
    leave_rows = ""
    for code, label in (("CL", "Casual Leave (CL)"), ("SL", "Sick Leave (SL)"),
                        ("EL", "Earned Leave (EL)")):
        o = op.get(code, 0)
        a = lv[code]
        leave_rows += (f"<tr><td><b>{label}</b></td><td class='n'>{o:g}</td>"
                       f"<td class='n'>0</td><td class='n'>{o:g}</td>"
                       f"<td class='n'>{a:g}</td><td class='n'><b>{o - float(a):g}</b></td></tr>")

    # ── Pro-rate note ──
    frac_note = ""
    if res["month_fraction"] != 1:
        frac_note = (f" &middot; allowance &amp; incentive pro-rated to "
                     f"{float(res['month_fraction']) * 100:.0f}% "
                     f"({res['active_paid_days']}/{res['paid_days']} paid days)")

    # ── Logo ──
    logo_src = _logo()
    logo_html = f'<img src="{logo_src}" alt="Genartml">' if logo_src else ''

    # ── Reimbursements total ──
    reimb_cell = (_r(res['reimbursements'])
                  if res['reimbursements']
                  else "<span class='muted'>N/A</span>")

    return f"""
<div class="page">
  <!-- ═══════════════════ HEADER ═══════════════════ -->
  <div class="hdr">
    <div class="brand">
      {logo_html}
      <div>
        <div class="brand-name">{branding.get('company_name', 'COMPANY')}</div>
        <div class="cin">CIN: {branding.get('cin', 'N/A')} &nbsp;|&nbsp; EPF Reg. No: {branding.get('epf', 'N/A')}</div>
      </div>
    </div>
    <div class="for-box">
      <div class="for-label">Payslip For</div>
      <div class="for-month">{MONTHS[month]} {year}</div>
    </div>
  </div>

  <!-- ═══════════════════ BANNER ═══════════════════ -->
  <div class="banner">Payslip for the month of {MONTHS[month]} {year}</div>

  <!-- ═══════════════════ EMPLOYEE INFO ═══════════════════ -->
  <table class="meta">{_meta_rows(res, year, month, branding)}</table>

  <!-- ═══════════════════ EARNINGS & DEDUCTIONS ═══════════════════ -->
  <div class="cols">
    <div><table class="sec">
      <tr><th>Earnings</th><th class="n">Month (₹)</th></tr>
      {rows(earn)}
      <tr class="tot"><td><b>Gross Earnings (A)</b></td><td class="n">{_r(res['gross'])}</td></tr>
    </table></div>
    <div><table class="sec">
      <tr><th>Deductions</th><th class="n">Month (₹)</th></tr>
      {rows(ded)}
      <tr class="tot"><td><b>Total Deductions (B)</b></td><td class="n">{_r(ded_total)}</td></tr>
    </table></div>
  </div>

  <!-- ═══════════════════ REIMBURSEMENTS & OVERTIME ═══════════════════ -->
  <div class="cols">
    <div><table class="sec">
      <tr><th>Reimbursements (Non-Taxable)</th><th class="n"></th></tr>
      <tr><td>Internet / Telephone</td><td class="n muted">N/A</td></tr>
      <tr><td>Fuel / Travel</td><td class="n muted">N/A</td></tr>
      <tr class="tot"><td><b>Total Reimbursements (C)</b></td>
        <td class="n">{reimb_cell}</td></tr>
    </table></div>
    <div><table class="sec">
      <tr><th>Overtime &amp; Pay Basis</th><th class="n"></th></tr>
      <tr><td>Approved OT Hours</td><td class="n">{float(round(res['ot_hours'], 2)):g} hrs</td></tr>
      <tr><td>OT Rate / hr (÷8 basis)</td><td class="n">{_r(res['ot_rate'])}</td></tr>
      <tr class="tot"><td><b>OT Payable</b></td><td class="n">{_r(res['ot_payable'])}</td></tr>
    </table></div>
  </div>

  <!-- ═══════════════════ NET PAY ═══════════════════ -->
  <div class="net">
    <div>
      <div class="lbl">NET PAY (Take Home)</div>
      <div class="sub">= Gross Earnings (A) − Deductions (B) + Reimbursements (C)</div>
    </div>
    <div class="amt">{_r(res['net_pay'])}</div>
  </div>
  <div class="words">Amount in words: <i>{_words(res['net_pay'])}</i></div>

  <!-- ═══════════════════ LEAVE BALANCE ═══════════════════ -->
  {
  f'''<table class="leave">
    <tr><th>Leave Balance</th><th class="n">Opening</th><th class="n">Credited</th>
        <th class="n">Available</th><th class="n">Availed</th><th class="n">Balance</th></tr>
    {leave_rows}
  </table>''' if branding.get('show_leave_balance', True) else ''
  }

  {flags_html}

  <!-- ═══════════════════ FOOTER ═══════════════════ -->
  <div class="foot">
    <div>Professional Tax: Gujarat slab ({_r(res['professional_tax'])}/mo)</div>
    <div>CTC: ₹{float(e['ctc_monthly']):,.0f}/mo · 70/20/10 split{frac_note}</div>
  </div>
  <div class="center">{branding.get('footer_text', 'This is a system-generated payslip.')}</div>
</div>"""


def render_all(results, year, month, out_html):
    """Render all employee payslips into a single multi-page HTML file."""
    branding = get_branding()
    css = generate_css(branding)
    body = "".join(render_payslip(r, year, month) for r in results)
    html = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Payslips — {MONTHS[month]} {year}</title>"
            f"<style>{css}\n@page {{ size:A4; margin:10mm; }}</style></head>"
            f"<body>{body}</body></html>")
    Path(out_html).write_text(html, encoding="utf-8")
    return out_html
