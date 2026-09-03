#!/usr/bin/env python3
"""
Genartml Payroll — local web app.

    python3 app.py     then open http://127.0.0.1:5000

Runs entirely on your machine. Nothing is uploaded anywhere.
"""

import datetime as dt
import io
import json
import shutil
import traceback
import logging
from logging.handlers import RotatingFileHandler
from decimal import Decimal
from pathlib import Path
import os
from functools import wraps

import secrets

from flask import (
    Flask,
    request,
    session,
    jsonify,
    redirect,
    send_from_directory,
)


from engine import CompanyCalendar, Rules, run_payroll, PayrollError
from timesheet import read_workbook
from payslip import render_all, render_payslip, CSS, MONTHS
from run_payroll import write_summary, match_employee
import finance as FIN

HERE = Path(__file__).parent
CONFIG = HERE / "config"

# Vercel's filesystem is read-only; use /tmp for writable dirs
if os.environ.get("VERCEL"):
    UPLOADS = Path("/tmp/timesheets")
    OUT = Path("/tmp/out")
    LOGS = Path("/tmp/logs")
else:
    UPLOADS = HERE / "timesheets"
    OUT = HERE / "out"
    LOGS = HERE / "logs"
try:
    UPLOADS.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
except OSError:
    pass

app = Flask(__name__, static_folder=str(HERE / "public"))
app.debug = False
app.config.update({
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "SESSION_COOKIE_SECURE": True,
    "PREFERRED_URL_SCHEME": "https",
    "MAX_CONTENT_LENGTH": 16 * 1024 * 1024  # 16 MB upload limit
})
app.secret_key = os.environ.get("SECRET_KEY", "genartml-payroll-secret-2026")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify(error="Unauthorized"), 401
        return f(*args, **kwargs)
    return decorated

@app.before_request
def check_auth():
    # Only protect /api/ routes, but exclude /api/login
    if request.path.startswith("/api/") and request.path != "/api/login":
        if not session.get("logged_in"):
            return jsonify(error="Unauthorized"), 401

# Set up production logging
log_file = LOGS / "app.log"

# ---- Add security headers for every response ----
@app.after_request
def set_security_headers(response):
    # Content Security Policy – allow self and inline scripts (required for existing inline JS)
    csp = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Remove server header if present
    response.headers.pop('Server', None)
    return response

try:
    file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
except OSError:
    pass  # Vercel: can't write log files, use stdout instead
app.logger.setLevel(logging.INFO)
app.logger.info("Genartml Payroll startup")

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled Exception: {e}\n{traceback.format_exc()}")
    return jsonify(error="An internal server error occurred. Please check the logs."), 500


def _json(path):
    return json.loads(Path(path).read_text())


def _save_json(path, data):
    p = Path(path)
    if p.exists():
        shutil.copy(p, p.with_suffix(p.suffix + ".bak"))
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _dec(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    if isinstance(o, dict):
        return {k: _dec(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_dec(v) for v in o]
    return o


# ------------------------------------------------------------------ pages

# ------------------------------------------------------------------ auth / pages

@app.post("/api/login")
def login():
    data = request.get_json(force=True)
    username = data.get("u")
    password = data.get("p")
    # Default credentials
    if username == "admin" and password == "genartml2026":
        session["logged_in"] = True
        # Create CSRF token for this session
        session["csrf_token"] = secrets.token_hex(16)
        return jsonify(ok=True, csrf=session["csrf_token"]) 
    return jsonify(error="Invalid username or password"), 401


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/login")
def login_page():
    return send_from_directory(app.static_folder, "login.html")

@app.get("/")
def index():
    if not session.get("logged_in"):
        return redirect("/login")
    return send_from_directory(app.static_folder, "index.html")


@app.get("/static/<path:f>")
def static_files(f):
    return send_from_directory(app.static_folder, f)


# ------------------------------------------------------------------ config

@app.get("/api/config/<name>")
def get_config(name):
    if name not in ("rules", "employees", "calendar_2026"):
        return jsonify(error="Unknown config"), 404
    return jsonify(_json(CONFIG / f"{name}.json"))


@app.post("/api/config/<name>")
def set_config(name):
    if name not in ("rules", "employees", "calendar_2026"):
        return jsonify(error="Unknown config"), 404
    try:
        data = request.get_json(force=True)
        _save_json(CONFIG / f"{name}.json", data)
        Rules()
        CompanyCalendar()
        return jsonify(ok=True, message="Saved. A backup of the previous version was kept.")
    except Exception as e:
        return jsonify(error=str(e)), 400


# ------------------------------------------------------------------ calendar

@app.get("/api/calendar/<int:year>/<int:month>")
def calendar_breakdown(year, month):
    try:
        return jsonify(_dec(CompanyCalendar().breakdown(year, month)))
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.get("/api/calendar/<int:year>/all")
def calendar_year(year):
    cal = CompanyCalendar()
    return jsonify([{"month": m, "name": MONTHS[m], **_dec(cal.breakdown(year, m))}
                    for m in range(1, 13)])


# ------------------------------------------------------------------ files

@app.get("/api/timesheets")
def list_timesheets():
    return jsonify(sorted(
        [{"name": p.name, "size": p.stat().st_size,
          "modified": dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%d %b %Y, %H:%M")}
         for p in UPLOADS.glob("*.xlsx")], key=lambda x: x["name"], reverse=True))


@app.post("/api/timesheets")
def upload_timesheet():
    f = request.files.get("file")
    if not f or not f.filename.endswith((".xlsx", ".xlsm")):
        return jsonify(error="Upload an .xlsx timesheet workbook."), 400
    dest = UPLOADS / Path(f.filename).name
    f.save(dest)
    return jsonify(ok=True, name=dest.name)


@app.post("/api/timesheets/delete")
def delete_timesheet():
    name = request.get_json(force=True).get("name", "")
    p = UPLOADS / Path(name).name
    if p.exists():
        p.unlink()
    return jsonify(ok=True)


# ------------------------------------------------------------------ preview

@app.post("/api/preview")
def preview():
    """Read a workbook and report which tabs match which employee. No maths."""
    body = request.get_json(force=True)
    path = UPLOADS / Path(body["timesheet"]).name
    year, month = (int(x) for x in body["month"].split("-"))
    try:
        rules = Rules()
        sheets = read_workbook(path, rules, year, month)
        master = _json(CONFIG / "employees.json")
        tabs = []
        for tab, data in sheets.items():
            emp = match_employee(tab, data["name"], master)
            tabs.append({
                "tab": tab, "sheet_name": data["name"], "rows": len(data["rows"]),
                "matched": bool(emp),
                "employee": emp["name"] if emp else None,
                "emp_id": emp.get("emp_id") if emp else None,
                "ctc": emp.get("ctc_monthly") if emp else None,
            })
        return jsonify(tabs=tabs, unmatched=[t for t in tabs if not t["matched"]])
    except PayrollError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"{e}"), 400


# ------------------------------------------------------------------ run

def _prepare(body):
    path = UPLOADS / Path(body["timesheet"]).name
    year, month = (int(x) for x in body["month"].split("-"))
    rules, cal = Rules(), CompanyCalendar()
    bd = cal.breakdown(year, month)
    wd = int(body.get("working_days_override") or bd["working_days"])
    sheets = read_workbook(path, rules, year, month)
    master = _json(CONFIG / "employees.json")

    excluded = set(body.get("exclude_ot_dates") or [])
    pairs, missing = [], []
    for tab, data in sheets.items():
        emp = match_employee(tab, data["name"], master)
        if not emp:
            missing.append(f"{data['name']} ({tab})")
            continue
        emp = dict(emp)
        emp["ctc_monthly"] = Decimal(str(emp["ctc_monthly"]))
        for k in ("date_of_joining", "exit_date"):
            if emp.get(k):
                d = dt.date.fromisoformat(emp[k])
                emp[k] = d
                if k == "date_of_joining":
                    emp["doj_display"] = d.strftime("%d-%m-%Y")
        rows = []
        for r in data["rows"]:
            r = dict(r)
            key = f"{emp.get('emp_id')}|{r['date'].isoformat()}"
            if key in excluded:
                r["approved_ot_hours"] = Decimal(0)
            rows.append(r)
        pairs.append((emp, rows))
    return pairs, missing, wd, rules, cal, year, month, bd


@app.post("/api/run")
def run():
    body = request.get_json(force=True)
    try:
        pairs, missing, wd, rules, cal, year, month, bd = _prepare(body)
        if missing:
            return jsonify(error="No employee record for: " + ", ".join(missing)
                           + ". Add them under Employees first — CTC is never guessed."), 400
        results = run_payroll(pairs, wd, rules, cal, year, month)
        results.sort(key=lambda r: r["employee"].get("emp_id", ""))

        outdir = OUT / f"{year}-{month:02d}"
        outdir.mkdir(parents=True, exist_ok=True)
        render_all(results, year, month, outdir / "payslips.html")
        write_summary(results, outdir / "payroll_summary.xlsx", year, month, bd)

        rows = []
        for r in results:
            e = r["employee"]
            rows.append({
                "name": e["name"], "emp_id": e.get("emp_id"),
                "ctc": float(e["ctc_monthly"]),
                "per_day": float(r["per_day"]), "per_hour": float(r["per_hour"]),
                "ot_rate": float(r["ot_rate"]),
                "payable_days": float(r["payable_days"]),
                "lop_days": float(r["lop_days"]),
                "ot_hours": float(r["ot_hours"]),
                "base_earned": float(r["base_earned"]),
                "ot_payable": float(r["ot_payable"]),
                "allowance": float(r["allowance_paid"]),
                "incentive": float(r["incentive_paid"]),
                "gross": float(r["gross"]),
                "ptax": float(r["professional_tax"]),
                "net": float(r["net_pay"]),
                "month_fraction": float(r["month_fraction"]),
                "flags": r["flags"],
                "type_counts": r["type_counts"],
            })
        return jsonify(
            month=f"{MONTHS[month]} {year}", month_key=f"{year}-{month:02d}",
            breakdown=_dec(bd), working_days=wd,
            override=bool(body.get("working_days_override")),
            rows=rows,
            totals={k: round(sum(r[k] for r in rows), 2) for k in
                    ("base_earned", "ot_payable", "allowance", "incentive",
                     "gross", "ptax", "net")},
            flag_count=sum(len(r["flags"]) for r in rows),
        )
    except PayrollError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=f"{type(e).__name__}: {e}"), 400


@app.post("/api/ot-rows")
def ot_rows():
    """Every row carrying approved OT, so the UI can let you toggle them off."""
    body = request.get_json(force=True)
    try:
        path = UPLOADS / Path(body["timesheet"]).name
        year, month = (int(x) for x in body["month"].split("-"))
        rules = Rules()
        sheets = read_workbook(path, rules, year, month)
        master = _json(CONFIG / "employees.json")
        out = []
        for tab, data in sheets.items():
            emp = match_employee(tab, data["name"], master)
            if not emp:
                continue
            for r in data["rows"]:
                if r["approved_ot_hours"] and r["approved_ot_hours"] > 0:
                    out.append({
                        "key": f"{emp.get('emp_id')}|{r['date'].isoformat()}",
                        "employee": emp["name"], "emp_id": emp.get("emp_id"),
                        "date": r["date"].isoformat(),
                        "type": r["type"],
                        "approved": float(r["approved_ot_hours"]),
                        "device": float(r["device_ot_hours"]) if r["device_ot_hours"] is not None else None,
                        "has_clock": bool(r["check_in"] or r["check_out"]),
                        "note": r["note"] or "",
                    })
        out.sort(key=lambda x: (x["employee"], x["date"]))
        return jsonify(rows=out)
    except Exception as e:
        return jsonify(error=str(e)), 400


# ------------------------------------------------------------------ payslips

@app.post("/api/payslip-html")
def payslip_html():
    body = request.get_json(force=True)
    try:
        pairs, missing, wd, rules, cal, year, month, bd = _prepare(body)
        results = run_payroll(pairs, wd, rules, cal, year, month)
        who = body.get("emp_id")
        if who:
            results = [r for r in results if r["employee"].get("emp_id") == who]
        if not results:
            return jsonify(error="No matching employee."), 404
        body_html = "".join(render_payslip(r, year, month) for r in results)
        return (f"<!doctype html><meta charset='utf-8'><style>{CSS}"
                f"@page{{size:A4;margin:10mm}} body{{padding:14px}}</style>{body_html}")
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.post("/api/payslip-download")
def payslip_download():
    """Generate a single employee payslip as a downloadable HTML file."""
    body = request.get_json(force=True)
    try:
        pairs, missing, wd, rules, cal, year, month, bd = _prepare(body)
        results = run_payroll(pairs, wd, rules, cal, year, month)
        who = body.get("emp_id")
        if who and who != "ALL":
            results = [r for r in results if r["employee"].get("emp_id") == who]
        if not results:
            return jsonify(error="No matching employee."), 404

        # Save individual payslips to out/<month>/ directory
        mk = f"{year}-{month:02d}"
        outdir = OUT / mk
        outdir.mkdir(parents=True, exist_ok=True)

        # Generate combined HTML
        body_html = "".join(render_payslip(r, year, month) for r in results)
        full_html = (f"<!doctype html><html><head><meta charset='utf-8'>"
                     f"<title>Genartml Payslip {MONTHS[month]} {year}</title>"
                     f"<style>{CSS}\n@page {{ size:A4; margin:10mm; }}</style></head>"
                     f"<body>{body_html}</body></html>")

        if who and who != "ALL":
            name = results[0]["employee"].get("name", who).replace(" ", "_")
            fname = f"payslip-{mk}-{name}.html"
        else:
            fname = f"payslips-{mk}-all.html"
            # Also save the combined file
            render_all(results, year, month, outdir / "payslips.html")
            write_summary(results, outdir / "payroll_summary.xlsx", year, month, bd)

        buf = io.BytesIO(full_html.encode("utf-8"))
        return send_file(buf, mimetype="text/html", as_attachment=True,
                         download_name=fname)
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.get("/api/download/<month_key>/<kind>")
def download(month_key, kind):
    outdir = OUT / month_key
    files = {"summary": ("payroll_summary.xlsx", "payroll_summary.xlsx"),
             "html": ("payslips.html", "payslips.html")}
    
    if kind not in files and kind != "pdf":
        return jsonify(error="Unknown file"), 404

    html_src = outdir / "payslips.html"
    xlsx_src = outdir / "payroll_summary.xlsx"
    
    if not html_src.exists() or not xlsx_src.exists():
        runs = FIN.store().list_payroll(month_key)
        if not runs:
            return jsonify(error="Run payroll first or select an archived month."), 404
        results = runs[0]["detail"]
        if not results or "employee" not in results[0]:
            return jsonify(error="This month was recorded with an older version of the software that didn't save the full details. Please run payroll again to download its payslips."), 400
            
        year, month = (int(x) for x in month_key.split("-"))
        outdir.mkdir(parents=True, exist_ok=True)
        bd = CompanyCalendar().breakdown(year, month)
        render_all(results, year, month, html_src)
        write_summary(results, xlsx_src, year, month, bd)

    if kind == "pdf":
        try:
            from weasyprint import HTML
            buf = io.BytesIO()
            HTML(str(html_src)).write_pdf(buf)
            buf.seek(0)
            return send_file(buf, mimetype="application/pdf", as_attachment=True,
                             download_name=f"genartml-payslips-{month_key}.pdf")
        except ImportError:
            return jsonify(error="PDF needs weasyprint. Run: pip install weasyprint. "
                                 "You can still download the HTML and print it."), 400

    f, dl = files[kind]
    p = outdir / f
    return send_file(p, as_attachment=True, download_name=f"genartml-{month_key}-{dl}")


# ------------------------------------------------------------------ finance

@app.get("/api/finance/status")
def fin_status():
    s = FIN.load_secrets()
    st = FIN.store()
    ok, msg = True, "Saving to the local database on this computer."
    if st.name == "supabase":
        try:
            st.ping()
            msg = "Connected to Supabase."
        except Exception as e:
            ok, msg = False, str(e)
    return jsonify(backend=st.name, ok=ok, message=msg,
                   url=s.get("supabase_url", ""), bucket=s.get("bucket", "invoices"),
                   has_key=bool(s.get("supabase_key")),
                   categories=FIN.EXPENSE_CATEGORIES)


@app.post("/api/finance/connect")
def fin_connect():
    b = request.get_json(force=True)
    url = (b.get("url") or "").strip().rstrip("/")
    key = (b.get("key") or "").strip()
    bucket = (b.get("bucket") or "invoices").strip()

    if not url.startswith("https://"):
        return jsonify(error="The project URL should look like "
                             "https://yourproject.supabase.co"), 400
    if not key:
        cur = FIN.load_secrets()
        key = cur.get("supabase_key", "")
        if not key:
            return jsonify(error="Paste your key."), 400

    kind = FIN.key_kind(key)
    if kind == "publishable":
        return jsonify(
            error="That is the publishable key. Publishable keys are meant for "
                  "browsers and cannot read these tables, because row-level "
                  "security is on and no policy grants anon access. This app runs "
                  "as a server on your own machine, so use the SECRET key "
                  "(sb_secret_… or the legacy service_role JWT) — it never reaches "
                  "a browser. Supabase → Project Settings → API Keys."), 400

    (CONFIG / "secrets.json").write_text(json.dumps(
        {"supabase_url": url, "supabase_key": key, "bucket": bucket}, indent=2))
    FIN.reset()
    st = FIN.store()
    try:
        st.ping()
    except Exception as e:
        return jsonify(error=f"Saved the details, but the connection failed. {e}"), 400
    return jsonify(ok=True, backend=st.name, key_kind=kind)


@app.get("/api/finance/diagnose")
def fin_diagnose():
    """Step-by-step check so a failure says which step broke."""
    st = FIN.store()
    if st.name != "supabase":
        return jsonify(steps=[{"step": "Backend", "ok": True,
                               "detail": "Using the local database. Nothing to check."}])
    return jsonify(steps=st.diagnose())


@app.post("/api/finance/disconnect")
def fin_disconnect():
    p = CONFIG / "secrets.json"
    if p.exists():
        p.unlink()
    FIN.reset()
    return jsonify(ok=True, backend=FIN.store().name)


@app.get("/api/expenses")
def exp_list():
    try:
        return jsonify(FIN.store().list_expenses(request.args.get("month") or None,
                                                 request.args.get("category") or None))
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.post("/api/expenses")
def exp_add():
    try:
        f = request.files.get("file")
        d = json.loads(request.form.get("data", "{}")) if request.form.get("data") \
            else request.get_json(force=True)
        for k in ("spent_on", "category", "amount"):
            if not d.get(k):
                return jsonify(error=f"{k.replace('_', ' ').title()} is required."), 400
        if d["category"] == "Salaries":
            return jsonify(error="Salaries are recorded from a payroll run, not added by "
                                 "hand — use Record salaries on the Run payroll screen."), 400
        d["amount"] = float(d["amount"])
        d["tax_amount"] = float(d.get("tax_amount") or 0)
        row = FIN.store().add_expense(d, f.read() if f else None, f.filename if f else None)
        return jsonify(ok=True, expense=row)
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=str(e)), 400


@app.post("/api/expenses/<eid>")
def exp_update(eid):
    try:
        FIN.store().update_expense(eid, request.get_json(force=True))
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.post("/api/expenses/<eid>/delete")
def exp_delete(eid):
    try:
        FIN.store().delete_expense(eid)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.get("/api/expenses/<eid>/file")
def exp_file(eid):
    data, name = FIN.store().get_file(eid)
    if not data:
        return jsonify(error="No file attached to this expense."), 404
    return send_file(io.BytesIO(data), as_attachment=True, download_name=name)


@app.get("/api/months")
def months():
    try:
        return jsonify(FIN.all_months())
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.get("/api/months/<month_key>")
def month_one(month_key):
    try:
        return jsonify(FIN.month_summary(month_key))
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.post("/api/payroll/archive")
def payroll_archive():
    """Save a completed payroll run so it counts as that month's salary spend."""
    b = request.get_json(force=True)
    try:
        pairs, missing, wd, rules, cal, year, month, bd = _prepare(b)
        if missing:
            return jsonify(error="No employee record for: " + ", ".join(missing)), 400
        results = run_payroll(pairs, wd, rules, cal, year, month)
        mk = f"{year}-{month:02d}"
        serialized = _dec(results)
        for d, r in zip(serialized, results):
            d["name"] = r["employee"].get("name")
            d["net"] = float(r["net_pay"])
            
        run = {
            "month_key": mk, "working_days": wd, "headcount": len(results),
            "total_base": float(sum(r["base_earned"] for r in results)),
            "total_ot": float(sum(r["ot_payable"] for r in results)),
            "total_allowance": float(sum(r["allowance_paid"] for r in results)),
            "total_incentive": float(sum(r["incentive_paid"] for r in results)),
            "total_gross": float(sum(r["gross"] for r in results)),
            "total_tax": float(sum(r["professional_tax"] for r in results)),
            "total_net": float(sum(r["net_pay"] for r in results)),
            "detail": serialized,
        }
        FIN.store().save_payroll(run)
        return jsonify(ok=True, month_key=mk, total_net=run["total_net"],
                       headcount=run["headcount"])
    except PayrollError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=str(e)), 400


@app.post("/api/payroll/archive/<month_key>/delete")
def payroll_unarchive(month_key):
    FIN.store().delete_payroll(month_key)
    return jsonify(ok=True)


@app.get("/api/selftest")
def selftest():
    import subprocess
    r = subprocess.run(["python3", "test_engine.py"], cwd=HERE,
                       capture_output=True, text=True)
    return jsonify(passed=(r.returncode == 0), output=r.stdout or r.stderr)


if __name__ == "__main__":
    app.logger.info("Starting local development server")
    print("\n  Genartml Payroll  →  http://127.0.0.1:5000")
    print("  WARNING: You are running the dev server. Use start.sh or start.bat for production.\n")
    app.run(port=5000, debug=False)
