# Genartml Payroll

Reads a monthly timesheet workbook, calculates salaries, and generates payslips.
Built for Genartml Pvt. Ltd. only — the rules, calendar, and branding are yours.

## Install

Needs Python 3.9+.

```bash
./setup.sh          # macOS / Linux
setup.bat           # Windows
```

That installs the dependencies and runs the 34-check self-test so you know
straight away whether it works on your machine.

## Use the app (recommended)

```bash
python3 app.py
```

Open **http://127.0.0.1:5000**. Everything runs on your computer — no hosting,
no account, nothing uploaded anywhere.

Six screens:

| Screen | What you do there |
|---|---|
| **Run payroll** | Pick a workbook and month, calculate, view and download payslips. |
| **Money** | Every rupee spent, by month. Invoices, categories, salary totals. |
| **Employees** | CTC, PAN, bank, joining and exit dates, opening leave balances. |
| **Pay rules** | Salary split, OT multiplier, every day type's pay factor, tax slabs. |
| **Holidays** | The 2026 calendar. Edit a holiday and working days recalculate. |
| **Timesheets** | Upload and manage monthly workbooks. |
| **Self-test** | Run the 34 checks any time you change a rule. |

**Review overtime** on the Run screen lists every approved OT entry with its
problems marked — no clock trail, above the device log, on an unpaid day.
Untick anything you don't want to pay and re-run. Nothing is written back to
your timesheet.

## Tracking money

**Money → Add invoice** stores the spend and the invoice file together. Date,
category, vendor, amount, GST, invoice number, paid/due, and the PDF or photo.
Everything rolls up by month automatically.

Salaries are not typed in by hand. Run payroll, then press **Record salaries in
Money** on the results — the month's net total and per-person breakdown are saved
as that month's salary spend. Re-recording the same month replaces it, so
correcting a run is safe.

The Overview shows what you spent this month, all time, the salary share, and a
breakdown by category. Click any month for its full detail: every employee paid
and every invoice filed.

### Where it's stored

By default: `data/genartml.db` on this computer, with invoice files in
`data/invoices/`. Nothing to set up, works offline, but it only exists on this
machine — back the `data/` folder up.

**To use Supabase instead:**

1. Supabase → SQL Editor → paste and run `config/supabase_schema.sql`. That creates
   both tables and the private `invoices` storage bucket.
2. Supabase → Project Settings → API Keys → copy the **secret** key
   (`sb_secret_…`).
3. In the app: **Money → Database**, paste the project URL and the secret key,
   press Connect. Then press **Test connection** — it checks the project, the key
   type, both tables, a write, and the storage bucket separately, so a failure tells
   you exactly which step broke.

### Why the secret key and not the publishable one

The publishable key is designed to be public — it ships inside browsers. Payroll
and expense data must not be readable by anyone holding it, so the schema keeps
row-level security **on** with no anon policy. The publishable key therefore cannot
read these tables, and the app refuses it with an explanation rather than saving a
setup that will not work.

This app is a server running on your own machine. The browser talks to your Flask
app, never to Supabase directly, so the secret key sits in `config/secrets.json`
(gitignored) and never reaches a browser. That is the correct place for it.

## Command line (same engine, no browser)

```bash
python run_payroll.py --timesheet /path/to/Employee_Timesheet_August_2026.xlsx --month 2026-08
```

Output lands in `out/2026-08/`:

| File | What it is |
|---|---|
| `payslips.html` | One page per employee. Open in a browser, Cmd/Ctrl+P → Save as PDF. |
| `payslips.pdf` | Same thing, pre-rendered, if weasyprint is installed. |
| `payroll_summary.xlsx` | Full working: per-day rate, OT rate, payable days, gross, net. |
| `review_flags.txt` | Everything the engine wants a human to look at before you pay. |

Add `--strict` to make the run exit non-zero if any flag is raised. Useful if you
ever wire this into a scheduled job.

## Every month, you do three things

1. **Update the timesheet workbook** as you already do — one tab per employee,
   column C is the day Type, column J is Approved OT hours.
2. **Run the command above** with the new month.
3. **Read `review_flags.txt`** and decide on anything listed. Then send the payslips.

That's it. Working days, weekly offs, and public holidays are computed from
`config/calendar_2026.json` automatically. September will correctly come out at 21
working days without you touching anything.

## The bug this exists to prevent

Your previous software computed:

```
per_day = basic / days_present        # 21,000 / 15 = 1,400  → OT rate 350
```

It must be:

```
per_day = basic / working_days        # 21,000 / 20 = 1,050  → OT rate 262.50
```

`working_days` is a **month constant** — the same number for every employee, derived
only from the company calendar. `engine.run_payroll()` raises `PayrollError` and
halts the entire run if two employees in one month ever receive different divisors.
`test_engine.py` asserts the Sandeep golden case explicitly: OT rate must be 262.50,
never 350.00; net must be 33,283.75, never 35,375.00.

Run the tests any time you change a rule:

```bash
python3 test_engine.py      # 41 checks on the payroll engine
python3 test_supabase.py    # 22 checks on the database layer
```

Both exit non-zero on any failure. `test_supabase.py` runs a stand-in Supabase
server on localhost, so it verifies the insert, update, delete, file upload,
download and payroll-archive paths without touching your real project.

## Configuration

Everything editable lives in `config/`. No rates are hardcoded in the Python.

### `rules.json`

- `ctc_split` — the 70/20/10 split and the 50% incentive payout.
- `overtime.multiplier` — currently `2.0`. Change once, applies everywhere.
- `overtime.rounding` — `none` (default) or `floor_30min`. Never rounds up.
- `professional_tax_gujarat` — the slab table.
- `pay_factors` — every day type, its pay factor, and whether it counts toward
  working days. **Adding a new day type?** Add it here. The engine refuses to
  guess a factor for an unknown type; it raises an error instead of silently
  paying 100%.
- `exit_policy` — whether allowance and incentive pro-rate on a mid-month exit.

### `calendar_2026.json`

Straight from your Holiday & Leave Calendar 2026. Note the engine follows Section C:
a holiday landing on a Saturday or Sunday gets no compensatory day, so it is **not**
subtracted twice. Independence Day 2026 falls on a Saturday, which is why August has
20 working days and not 19.

For 2027, copy this file to `calendar_2027.json` and update the dates.

### `employees.json`

The master. CTC, PAN, bank details, designation, joining date. The timesheet has no
salary data in it, so this file is where CTC lives.

- `aliases` — handles spelling drift. The August tab says "Prashant Songagra" while
  his payslip says "Songara"; the alias catches it.
- `exit_date` — set it and allowance + incentive pro-rate automatically.
- `leave_opening` — CL/SL/EL balances at the start of the month, for the payslip's
  leave table.

If an employee tab has no master entry, the run **stops**. It will not invent a CTC.

## Review flags

These never block payment. They print to console and to `review_flags.txt`.

| Code | Means |
|---|---|
| `OT_ON_UNPAID_DAY` | Approved OT on an LWP or Absent day — 0% base but paid overtime. |
| `OT_WITHOUT_CLOCK_TRAIL` | Approved OT with no check-in and no check-out. |
| `OT_EXCEEDS_DEVICE_LOG` | Approved OT is higher than what the machine logged. |
| `TYPE_CONTRADICTS_CLOCK` | Punches recorded on a Week Off or leave day. |
| `MISSING_PUNCH` | An Office day missing a punch. |
| `OT_RATIO_HIGH` | OT exceeds 30% of base earned for that person. |
| `DUPLICATE_DATE` | Same date twice in one tab. |
| `PAYABLE_EXCEEDS_WORKING` | Payable days > working days. Something is misclassified. |
| `WORKING_DAYS_MISMATCH` | **Halts the run.** The divisor bug. |

## Overnight shifts

The timesheet stores bare times, so a shift running 19:12 → 00:30 has a checkout
numerically smaller than the check-in. `timesheet.py` detects this and rolls the
checkout to the next day before anything else reads it. Without that, the day looks
like an 18-hour early departure and real overtime disappears.

Long term, store check-out as a full date+time in the workbook.

## Adding an employee

Add a tab to the timesheet, add an entry to `config/employees.json`. Nothing else.

## Files

```
payroll/
├── app.py                web app — start here
├── static/index.html     the interface
├── run_payroll.py        command-line version
├── finance.py            expenses + invoice storage (SQLite or Supabase)
├── engine.py             calculation — the divisor assertion lives here
├── timesheet.py          workbook reader, overnight-shift fix
├── payslip.py            HTML/PDF payslip rendering
├── test_engine.py        41 payroll checks
├── test_supabase.py      22 database checks (uses a local stand-in)
├── setup.sh / setup.bat  one-time install
├── config/
│   ├── rules.json        rates, pay factors, PT slabs
│   ├── supabase_schema.sql  run this in Supabase first
│   ├── secrets.sample.json  copy to secrets.json to connect Supabase
│   ├── calendar_2026.json holidays and work week
│   └── employees.json    CTC and employee master
├── assets/               Genartml logo
└── data/                 local database + invoice files (back this up)
```
