"""
Stand-in Supabase. Speaks enough PostgREST and Storage to exercise
SupabaseStore end to end without touching a real project.

    python3 test_supabase.py
"""

import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import finance

ROWS = {"expenses": [], "payroll_runs": []}
BLOBS = {}
SECRET = "sb_secret_TESTKEY"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth(self):
        k = self.headers.get("apikey") or ""
        if k != SECRET:
            self._send(401, {"message": "Invalid API key"})
            return False
        return True

    def _send(self, code, obj=None, raw=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if raw is not None:
            self.wfile.write(raw)
        elif obj is not None:
            self.wfile.write(json.dumps(obj).encode())

    def _table(self):
        m = re.match(r"/rest/v1/(\w+)", self.path)
        return m.group(1) if m else None

    def _eq_id(self):
        m = re.search(r"id=eq\.([\w-]+)", self.path)
        return m.group(1) if m else None

    def _eq_month(self):
        from urllib.parse import unquote
        m = re.search(r"month_key=eq\.([\w%-]+)", self.path)
        return unquote(m.group(1)) if m else None

    def do_GET(self):
        if not self._auth():
            return
        if self.path.startswith("/storage/v1/object/"):
            from urllib.parse import unquote
            p = unquote(self.path.split("/storage/v1/object/", 1)[1])
            if p in BLOBS:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                self.wfile.write(BLOBS[p])
            else:
                self._send(404, {"message": "not found"})
            return
        if self.path.rstrip("/") == "/rest/v1":
            return self._send(200, {})
        t = self._table()
        if t not in ROWS:
            return self._send(404, {"message": f"relation {t} does not exist"})
        out = ROWS[t]
        mk = self._eq_month()
        if mk:
            out = [r for r in out if r.get("month_key") == mk]
        from urllib.parse import unquote, urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        if "category" in qs:
            want = unquote(qs["category"][0]).split("eq.", 1)[-1]
            out = [r for r in out if r.get("category") == want]
        self._send(200, out)

    def do_POST(self):
        if not self._auth():
            return
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        if self.path.startswith("/storage/v1/object/"):
            from urllib.parse import unquote
            BLOBS[unquote(self.path.split("/storage/v1/object/", 1)[1])] = body
            return self._send(200, {"Key": "ok"})
        t = self._table()
        if t not in ROWS:
            return self._send(404, {"message": "no such table"})
        row = json.loads(body)
        ROWS[t].append(row)
        self._send(201, [row])

    def do_PATCH(self):
        if not self._auth():
            return
        n = int(self.headers.get("Content-Length") or 0)
        patch = json.loads(self.rfile.read(n))
        t, rid = self._table(), self._eq_id()
        for r in ROWS.get(t, []):
            if r.get("id") == rid:
                r.update(patch)
        self._send(204)

    def do_DELETE(self):
        if not self._auth():
            return
        if self.path.startswith("/storage/v1/object/"):
            from urllib.parse import unquote
            BLOBS.pop(unquote(self.path.split("/storage/v1/object/", 1)[1]), None)
            return self._send(200, {})
        t = self._table()
        rid, mk = self._eq_id(), self._eq_month()
        before = len(ROWS.get(t, []))
        if rid:
            ROWS[t] = [r for r in ROWS[t] if r.get("id") != rid]
        elif mk:
            ROWS[t] = [r for r in ROWS[t] if r.get("month_key") != mk]
        self._send(204 if len(ROWS[t]) != before or True else 404)


def main():
    srv = HTTPServer(("127.0.0.1", 8799), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.4)
    url = "http://127.0.0.1:8799"
    st = finance.SupabaseStore(url, SECRET, "invoices")
    fails = []

    def check(name, got, want):
        ok = got == want
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<46} {got}"
              + ("" if ok else f"   expected {want}"))
        if not ok:
            fails.append(name)

    print("\nSupabase code path (against a stand-in server)\n")
    check("ping", st.ping(), True)

    e = st.add_expense({"spent_on": "2026-08-12", "category": "Software & subscriptions",
                        "vendor": "OpenAI", "amount": 4200, "status": "paid"},
                       b"%PDF-1.4 test", "openai.pdf")
    check("insert returns a row", bool(e.get("id")), True)
    check("month_key derived", e["month_key"], "2026-08")
    check("file path namespaced by month", e["file_path"].startswith("2026-08/"), True)

    check("list all", len(st.list_expenses()), 1)
    check("filter by month", len(st.list_expenses("2026-08")), 1)
    check("filter by wrong month", len(st.list_expenses("2026-09")), 0)
    check("filter by category", len(st.list_expenses(None, "Software & subscriptions")), 1)

    data, name = st.get_file(e["id"])
    check("download the invoice back", (data, name), (b"%PDF-1.4 test", "openai.pdf"))

    st.update_expense(e["id"], {"amount": 5000, "spent_on": "2026-09-02"})
    row = st.list_expenses()[0]
    check("update amount", float(row["amount"]), 5000.0)
    check("update re-derives month_key", row["month_key"], "2026-09")

    run = {"month_key": "2026-08", "working_days": 20, "headcount": 7,
           "total_base": 109882.5, "total_ot": 33713.75, "total_allowance": 16200,
           "total_incentive": 16200, "total_gross": 175996.25, "total_tax": 1350,
           "total_net": 174646.25, "detail": [{"name": "Sandeep Bhagat", "net": 33283.75}]}
    st.save_payroll(run)
    check("payroll saved", len(st.list_payroll()), 1)
    st.save_payroll(run)
    check("re-saving replaces, not duplicates", len(st.list_payroll()), 1)
    check("payroll net stored", float(st.list_payroll()[0]["total_net"]), 174646.25)
    check("payroll filter by month", len(st.list_payroll("2026-08")), 1)

    st.delete_expense(e["id"])
    check("delete removes the row", len(st.list_expenses()), 0)
    check("delete removes the file too", len(BLOBS), 0)

    st.delete_payroll("2026-08")
    check("delete payroll", len(st.list_payroll()), 0)

    bad = finance.SupabaseStore(url, "sb_secret_WRONG", "invoices")
    try:
        bad.ping()
        check("a wrong key is rejected", False, True)
    except Exception:
        check("a wrong key is rejected", True, True)

    d = st.diagnose()
    check("diagnose runs every step", len(d) >= 5, True)
    check("diagnose reports all ok", all(x["ok"] for x in d), True)
    check("diagnose leaves nothing behind", (len(ROWS["expenses"]), len(BLOBS)), (0, 0))

    print("\n" + "-" * 62)
    if fails:
        print(f"  {len(fails)} FAILURE(S): " + ", ".join(fails))
        sys.exit(1)
    print("  Supabase code path verified.\n")


if __name__ == "__main__":
    main()
