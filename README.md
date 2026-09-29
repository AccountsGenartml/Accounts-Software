# Genartml Payroll & HR Suite 🚀

An enterprise-grade, privacy-first payroll calculation engine and HR management dashboard built exclusively for Genartml Pvt. Ltd.

This software automates monthly timesheet parsing (via AI), exact gross-to-net salary calculations (including EPF, ESI, and TDS compliance), dynamically generates branded PDF payslips, and stores financial records cleanly in a unified dashboard.

---

## ✨ Key Features

1. **AI-Powered "Magic" Timesheet Scanner**
   Upload raw biometric PDF logs or messy timesheets. The system uses Google Gemini AI to automatically extract, structure, and calculate total hours, overtime, and leave data without any manual data entry.
2. **Statutory Tax Compliance Engine**
   Legally compliant in India. The payroll engine automatically calculates and deducts EPF (12% of basic), ESI (0.75% of gross <= ₹21k), and custom TDS, straight from the UI. Toggle these on or off dynamically in the **Compliance** tab.
3. **Intelligent HR Chat Assistant**
   A proprietary, RAG-powered AI assistant that has secure access to your live company policies, employee leave balances, and holidays. It organizes answers beautifully and remembers your conversation history across multiple sessions.
4. **Dynamic Branding & Theming**
   Customize the output PDF payslips entirely from the UI. Add your CIN, EPF registration number, custom footer text, and inject a custom HEX theme color to match the company brand.
5. **Rock-Solid Payroll Math**
   The engine exists to prevent the infamous "working days divisor bug". It enforces a month-constant divisor based strictly on the company calendar (e.g., 20 working days in August), ensuring overtime rates and per-day rates are legally infallible.
6. **Expense & Finance Tracking**
   Every rupee spent is tracked by month. Upload invoices directly in the **Money** tab, categorize them, and monitor cash flow alongside the automated salary payouts.

---

## 🛠 Installation & Local Setup

The system requires **Python 3.9+**.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/AccountsGenartml/Accounts-Software.git
   cd Accounts-Software
   ```

2. **Install dependencies:**
   ```bash
   ./setup.sh          # macOS / Linux
   setup.bat           # Windows
   ```
   *This script installs dependencies and automatically runs the 41-check self-test suite to guarantee engine integrity on your machine.*

3. **Run the Dashboard:**
   ```bash
   python3 app.py
   ```
   Open **http://127.0.0.1:5001** in your browser. All processing happens locally; no sensitive employee data leaves your machine unless you explicitly connect a cloud database.

---

## ☁️ Vercel Cloud Deployment

The software is built to be deployed on Vercel for remote HR access. 

1. Push your code to a GitHub repository.
2. Import the repository into Vercel.
3. Add the following **Environment Variables** in Vercel:

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | **Required.** Powers the AI Timesheet Scanner and the HR Chat Assistant. |
| `SUPABASE_URL` | **Required.** The URL to your Supabase project for persistent cloud storage. |
| `SUPABASE_KEY` | **Required.** The `service_role` secret key for Supabase to bypass Row-Level Security. |
| `SECRET_KEY` | **Recommended.** A long random string used by Flask to encrypt browser sessions. |

*(Note: Vercel automatically injects `VERCEL=1`, which triggers the app to switch from local SQLite to your Supabase cloud database automatically).*

---

## 🗄 Architecture & File Structure

No rates or branding elements are hardcoded into Python. Everything is configurable.

```text
genartml-payroll/
├── app.py                # Core Flask backend & API router
├── static/index.html     # Unified Single-Page Application (SPA) frontend
├── engine.py             # The core mathematical payroll engine
├── payslip.py            # PDF and HTML payslip rendering logic
├── ai_parser.py          # Google Gemini PDF Timesheet extractor
├── finance.py            # Expense and invoice logic
├── db.py                 # SQLite local database driver
├── storage_bridge.py     # Supabase cloud storage driver
├── scripts/              # Helper scripts and legacy generation tools
├── config/               # System state (JSON files)
│   ├── rules.json        # CTC splits, OT multipliers, PT slabs
│   ├── calendar_2026.json# Working days and holiday calendar
│   ├── employees.json    # Employee master database (CTC, PAN, UAN)
│   ├── branding.json     # Custom payslip theme & company metadata
│   ├── compliance.json   # EPF, ESI, and TDS toggles
│   ├── chat_history.json # Multi-session HR Chat memory
│   └── supabase_schema.sql
└── demo_outputs/         # Generated output artifacts (Payslips, Summaries)
```

## 🔒 Security & Data Privacy

- **Local First:** If `SUPABASE_KEY` is not provided, the application defaults to saving all state, invoices, and employee configurations locally in the `data/` folder.
- **Strict Row-Level Security:** The `supabase_schema.sql` configures Supabase with Row Level Security (RLS) turned ON and no anonymous access policies. The publishable key cannot read this data.
- **Ephemeral Computing:** When deployed to Vercel, the engine stores zero persistent data on the server instances, seamlessly bridging all state to your connected Supabase.

---
*Built for Genartml Pvt. Ltd.*
