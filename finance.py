"""
Finance storage for Genartml.

Two backends, same interface:
  * Supabase  — when config/secrets.json has a url and key. Data lives in Postgres,
                invoice files go to Supabase Storage.
  * SQLite    — the default. A single file at data/genartml.db, invoice files in
                data/invoices/. Works with zero setup.

Switching backend does not change any calling code.
"""

import base64
import datetime as dt
from urllib.parse import quote
import json
import sqlite3
import uuid
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
FILES = DATA / "invoices"
DATA.mkdir(exist_ok=True)
FILES.mkdir(exist_ok=True)
SECRETS = HERE / "config" / "secrets.json"

EXPENSE_CATEGORIES = [
    "Salaries", "Software & subscriptions", "Hardware & equipment",
    "Rent & utilities", "Marketing & ads", "Contractors & freelancers",
    "Travel & transport", "Professional fees", "Office & supplies",
    "Taxes & compliance", "Other",
]


def load_secrets():
    if SECRETS.exists():
        try:
            return json.loads(SECRETS.read_text())
        except Exception:
            return {}
    return {}


def key_kind(key):
    """Tell a publishable key from a secret one, old format or new."""
    k = (key or "").strip()
    if k.startswith("sb_publishable_"):
        return "publishable"
    if k.startswith("sb_secret_"):
        return "secret"
    if k.count(".") == 2:                      # legacy JWT
        try:
            mid = k.split(".")[1]
            payload = json.loads(base64.urlsafe_b64decode(mid + "=" * (-len(mid) % 4)))
            role = payload.get("role")
            if role == "service_role":
                return "secret"
            if role == "anon":
                return "publishable"
        except Exception:
            pass
    return "unknown"


def backend_name():
    s = load_secrets()
    return "supabase" if (s.get("supabase_url") and s.get("supabase_key")) else "sqlite"


# ===================================================================== SQLite

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
  id TEXT PRIMARY KEY,
  spent_on TEXT NOT NULL,
  month_key TEXT NOT NULL,
  category TEXT NOT NULL,
  vendor TEXT,
  description TEXT,
  amount REAL NOT NULL,
  tax_amount REAL DEFAULT 0,
  payment_method TEXT,
  invoice_number TEXT,
  status TEXT DEFAULT 'paid',
  file_name TEXT,
  file_path TEXT,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exp_month ON expenses(month_key);

CREATE TABLE IF NOT EXISTS payroll_runs (
  id TEXT PRIMARY KEY,
  month_key TEXT NOT NULL UNIQUE,
  working_days INTEGER NOT NULL,
  headcount INTEGER NOT NULL,
  total_base REAL NOT NULL,
  total_ot REAL NOT NULL,
  total_allowance REAL NOT NULL,
  total_incentive REAL NOT NULL,
  total_gross REAL NOT NULL,
  total_tax REAL NOT NULL,
  total_net REAL NOT NULL,
  detail TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class SqliteStore:
    name = "sqlite"

    def __init__(self):
        self.db = DATA / "genartml.db"
        with self._c() as c:
            c.executescript(SCHEMA)

    def _c(self):
        c = sqlite3.connect(self.db)
        c.row_factory = sqlite3.Row
        return c

    # ---- expenses
    def add_expense(self, e, file_bytes=None, file_name=None):
        e = dict(e)
        e["id"] = e.get("id") or str(uuid.uuid4())
        e["created_at"] = dt.datetime.now().isoformat(timespec="seconds")
        e["month_key"] = e["spent_on"][:7]
        if file_bytes and file_name:
            safe = f"{e['id']}_{Path(file_name).name}"
            (FILES / safe).write_bytes(file_bytes)
            e["file_name"], e["file_path"] = file_name, safe
        cols = ["id", "spent_on", "month_key", "category", "vendor", "description",
                "amount", "tax_amount", "payment_method", "invoice_number", "status",
                "file_name", "file_path", "notes", "created_at"]
        with self._c() as c:
            c.execute(f"INSERT INTO expenses ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                      [e.get(k) for k in cols])
        return e

    def update_expense(self, eid, patch):
        patch = {k: v for k, v in patch.items()
                 if k in ("spent_on", "category", "vendor", "description", "amount",
                          "tax_amount", "payment_method", "invoice_number", "status", "notes")}
        if "spent_on" in patch:
            patch["month_key"] = patch["spent_on"][:7]
        if not patch:
            return
        sets = ",".join(f"{k}=?" for k in patch)
        with self._c() as c:
            c.execute(f"UPDATE expenses SET {sets} WHERE id=?", [*patch.values(), eid])

    def delete_expense(self, eid):
        with self._c() as c:
            row = c.execute("SELECT file_path FROM expenses WHERE id=?", (eid,)).fetchone()
            if row and row["file_path"]:
                p = FILES / row["file_path"]
                if p.exists():
                    p.unlink()
            c.execute("DELETE FROM expenses WHERE id=?", (eid,))

    def list_expenses(self, month_key=None, category=None):
        q, a = "SELECT * FROM expenses WHERE 1=1", []
        if month_key:
            q += " AND month_key=?"; a.append(month_key)
        if category:
            q += " AND category=?"; a.append(category)
        q += " ORDER BY spent_on DESC, created_at DESC"
        with self._c() as c:
            return [dict(r) for r in c.execute(q, a).fetchall()]

    def get_file(self, eid):
        with self._c() as c:
            r = c.execute("SELECT file_name,file_path FROM expenses WHERE id=?", (eid,)).fetchone()
        if not r or not r["file_path"]:
            return None, None
        p = FILES / r["file_path"]
        return (p.read_bytes(), r["file_name"]) if p.exists() else (None, None)

    # ---- payroll
    def save_payroll(self, run):
        run = dict(run)
        run["id"] = str(uuid.uuid4())
        run["created_at"] = dt.datetime.now().isoformat(timespec="seconds")
        run["detail"] = json.dumps(run["detail"])
        cols = ["id", "month_key", "working_days", "headcount", "total_base", "total_ot",
                "total_allowance", "total_incentive", "total_gross", "total_tax",
                "total_net", "detail", "created_at"]
        with self._c() as c:
            c.execute("DELETE FROM payroll_runs WHERE month_key=?", (run["month_key"],))
            c.execute(f"INSERT INTO payroll_runs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                      [run.get(k) for k in cols])
        return run

    def list_payroll(self, month_key=None):
        q, a = "SELECT * FROM payroll_runs", []
        if month_key:
            q += " WHERE month_key=?"; a.append(month_key)
        q += " ORDER BY month_key DESC"
        with self._c() as c:
            out = []
            for r in c.execute(q, a).fetchall():
                d = dict(r)
                d["detail"] = json.loads(d["detail"])
                out.append(d)
            return out

    def delete_payroll(self, month_key):
        with self._c() as c:
            c.execute("DELETE FROM payroll_runs WHERE month_key=?", (month_key,))


# =================================================================== Supabase

class SupabaseStore:
    name = "supabase"

    def __init__(self, url, key, bucket="invoices"):
        import requests
        self.requests = requests
        self.url = url.rstrip("/")
        self.key = key
        self.bucket = bucket
        self.h = {"apikey": key, "Authorization": f"Bearer {key}",
                  "Content-Type": "application/json"}

    def _rest(self, table):
        return f"{self.url}/rest/v1/{table}"

    def ping(self):
        r = self.requests.get(self._rest("expenses") + "?select=id&limit=1",
                              headers=self.h, timeout=15)
        if r.status_code == 404:
            raise RuntimeError("Connected, but there is no 'expenses' table. Run "
                               "config/supabase_schema.sql in the Supabase SQL editor.")
        if r.status_code in (401, 403):
            raise RuntimeError("The key was rejected. If it is a publishable key it "
                               "cannot read these tables — use the secret key.")
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase returned {r.status_code}: {r.text[:180]}")
        return True

    def diagnose(self):
        """Check each piece separately so a failure names the step that broke."""
        steps = []

        def add(step, ok, detail):
            steps.append({"step": step, "ok": ok, "detail": detail})
            return ok

        try:
            r = self.requests.get(f"{self.url}/rest/v1/", headers=self.h, timeout=15)
            add("Reach the project", r.status_code < 500,
                f"HTTP {r.status_code} from {self.url}")
        except Exception as e:
            add("Reach the project", False, f"Could not connect: {e}")
            return steps

        add("Key type", key_kind(self.key) == "secret",
            {"secret": "Secret key — correct for a server-side app.",
             "publishable": "Publishable key. Row-level security blocks it from "
                            "reading these tables. Use the secret key.",
             "unknown": "Key format not recognised."}[key_kind(self.key)])

        for table in ("expenses", "payroll_runs"):
            try:
                r = self.requests.get(self._rest(table) + "?select=id&limit=1",
                                      headers=self.h, timeout=15)
                if r.status_code == 404:
                    add(f"Table: {table}", False,
                        "Not found. Run config/supabase_schema.sql.")
                elif r.status_code in (401, 403):
                    add(f"Table: {table}", False,
                        "Access denied — the key cannot read this table.")
                elif r.status_code >= 400:
                    add(f"Table: {table}", False, f"HTTP {r.status_code}: {r.text[:120]}")
                else:
                    add(f"Table: {table}", True, "Readable.")
            except Exception as e:
                add(f"Table: {table}", False, str(e))

        # write + read back + clean up
        try:
            probe = {"id": str(uuid.uuid4()), "spent_on": "2000-01-01",
                     "month_key": "2000-01", "category": "Other", "vendor": "__probe__",
                     "amount": 0, "created_at": dt.datetime.now().isoformat(timespec="seconds")}
            r = self.requests.post(self._rest("expenses"), headers=self.h, json=probe, timeout=20)
            if r.status_code >= 400:
                add("Write a test row", False, f"HTTP {r.status_code}: {r.text[:140]}")
            else:
                add("Write a test row", True, "Insert succeeded.")
                self.requests.delete(f"{self._rest('expenses')}?id=eq.{probe['id']}",
                                     headers=self.h, timeout=20)
        except Exception as e:
            add("Write a test row", False, str(e))

        # storage bucket
        try:
            path = f"__probe__/{uuid.uuid4()}.txt"
            h = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
            r = self.requests.post(f"{self.url}/storage/v1/object/{self.bucket}/{quote(path)}",
                                   headers=h, data=b"probe", timeout=25)
            if r.status_code >= 400:
                add(f"Storage bucket '{self.bucket}'", False,
                    f"HTTP {r.status_code}: {r.text[:140]}. The schema file creates "
                    f"this bucket — check it ran.")
            else:
                add(f"Storage bucket '{self.bucket}'", True, "Upload succeeded.")
                self.requests.delete(f"{self.url}/storage/v1/object/{self.bucket}/{quote(path)}",
                                     headers=h, timeout=20)
        except Exception as e:
            add(f"Storage bucket '{self.bucket}'", False, str(e))

        return steps

    # ---- expenses
    def add_expense(self, e, file_bytes=None, file_name=None):
        e = dict(e)
        e["id"] = e.get("id") or str(uuid.uuid4())
        e["created_at"] = dt.datetime.now().isoformat(timespec="seconds")
        e["month_key"] = e["spent_on"][:7]
        if file_bytes and file_name:
            path = f"{e['month_key']}/{e['id']}_{Path(file_name).name}"
            up = self.requests.post(
                f"{self.url}/storage/v1/object/{self.bucket}/{quote(path)}",
                headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"},
                data=file_bytes, timeout=60)
            if up.status_code >= 400:
                raise RuntimeError(f"Invoice upload failed: {up.status_code} {up.text[:180]}")
            e["file_name"], e["file_path"] = file_name, path
        r = self.requests.post(self._rest("expenses"), headers={**self.h, "Prefer": "return=representation"},
                               json=e, timeout=25)
        if r.status_code >= 400:
            raise RuntimeError(f"Save failed: {r.status_code} {r.text[:200]}")
        return r.json()[0] if r.json() else e

    def update_expense(self, eid, patch):
        patch = {k: v for k, v in patch.items()
                 if k in ("spent_on", "category", "vendor", "description", "amount",
                          "tax_amount", "payment_method", "invoice_number", "status", "notes")}
        if "spent_on" in patch:
            patch["month_key"] = patch["spent_on"][:7]
        r = self.requests.patch(f"{self._rest('expenses')}?id=eq.{quote(str(eid), safe='')}",
                                headers=self.h, json=patch, timeout=25)
        if r.status_code >= 400:
            raise RuntimeError(r.text[:200])

    def delete_expense(self, eid):
        rows = self.list_expenses()
        row = next((x for x in rows if x["id"] == eid), None)
        if row and row.get("file_path"):
            self.requests.delete(f"{self.url}/storage/v1/object/{self.bucket}/{quote(row['file_path'])}",
                                 headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"},
                                 timeout=25)
        r = self.requests.delete(f"{self._rest('expenses')}?id=eq.{quote(str(eid), safe='')}", headers=self.h, timeout=25)
        if r.status_code >= 400:
            raise RuntimeError(r.text[:200])

    def list_expenses(self, month_key=None, category=None):
        # Values must be percent-encoded: category names contain "&" and spaces,
        # which would otherwise be read as extra query parameters.
        q = "?select=*&order=spent_on.desc"
        if month_key:
            q += f"&month_key=eq.{quote(str(month_key), safe='')}"
        if category:
            q += f"&category=eq.{quote(str(category), safe='')}"
        r = self.requests.get(self._rest("expenses") + q, headers=self.h, timeout=25)
        if r.status_code >= 400:
            raise RuntimeError(r.text[:200])
        return r.json()

    def get_file(self, eid):
        row = next((x for x in self.list_expenses() if x["id"] == eid), None)
        if not row or not row.get("file_path"):
            return None, None
        r = self.requests.get(f"{self.url}/storage/v1/object/{self.bucket}/{quote(row['file_path'])}",
                              headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"},
                              timeout=60)
        return (r.content, row["file_name"]) if r.status_code < 400 else (None, None)

    # ---- payroll
    def save_payroll(self, run):
        run = dict(run)
        run["id"] = str(uuid.uuid4())
        run["created_at"] = dt.datetime.now().isoformat(timespec="seconds")
        self.requests.delete(f"{self._rest('payroll_runs')}?month_key=eq.{quote(str(run['month_key']), safe='')}",
                             headers=self.h, timeout=25)
        r = self.requests.post(self._rest("payroll_runs"),
                               headers={**self.h, "Prefer": "return=representation"},
                               json=run, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Save failed: {r.status_code} {r.text[:200]}")
        return run

    def list_payroll(self, month_key=None):
        q = "?select=*&order=month_key.desc"
        if month_key:
            q += f"&month_key=eq.{quote(str(month_key), safe='')}"
        r = self.requests.get(self._rest("payroll_runs") + q, headers=self.h, timeout=25)
        if r.status_code >= 400:
            raise RuntimeError(r.text[:200])
        return r.json()

    def delete_payroll(self, month_key):
        self.requests.delete(f"{self._rest('payroll_runs')}?month_key=eq.{quote(str(month_key), safe='')}",
                             headers=self.h, timeout=25)


# ==================================================================== factory

_cache = {}


def store():
    s = load_secrets()
    if s.get("supabase_url") and s.get("supabase_key"):
        sig = (s["supabase_url"], s["supabase_key"], s.get("bucket", "invoices"))
        if _cache.get("sig") != sig:
            _cache["sig"] = sig
            _cache["obj"] = SupabaseStore(*sig)
        return _cache["obj"]
    if not isinstance(_cache.get("obj"), SqliteStore):
        _cache["obj"] = SqliteStore()
        _cache["sig"] = None
    return _cache["obj"]


def reset():
    _cache.clear()


# ============================================================ month roll-up

def month_summary(month_key):
    st = store()
    exp = st.list_expenses(month_key)
    pay = st.list_payroll(month_key)
    by_cat = {}
    for e in exp:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + float(e["amount"] or 0)
    salaries = float(pay[0]["total_net"]) if pay else 0.0
    if salaries:
        by_cat["Salaries"] = by_cat.get("Salaries", 0) + salaries
    other = sum(float(e["amount"] or 0) for e in exp)
    return {
        "month_key": month_key,
        "salaries": round(salaries, 2),
        "other_expenses": round(other, 2),
        "total": round(salaries + other, 2),
        "invoice_count": len(exp),
        "headcount": pay[0]["headcount"] if pay else 0,
        "by_category": {k: round(v, 2) for k, v in
                        sorted(by_cat.items(), key=lambda x: -x[1])},
        "payroll": pay[0] if pay else None,
    }


def all_months():
    st = store()
    keys = {e["month_key"] for e in st.list_expenses()}
    keys |= {p["month_key"] for p in st.list_payroll()}
    return [month_summary(k) for k in sorted(keys, reverse=True)]
