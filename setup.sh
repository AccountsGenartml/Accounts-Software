#!/usr/bin/env bash
# Genartml Payroll - one-time setup
set -e
echo "Genartml Payroll setup"
python3 --version || { echo "Python 3.9+ required. Install it first."; exit 1; }
echo "Installing dependencies..."
python3 -m pip install -r requirements.txt || \
  python3 -m pip install -r requirements.txt --break-system-packages
echo "Running self-test..."
python3 test_engine.py
echo ""
echo "Setup complete. Run a month with:"
echo "  python3 run_payroll.py --timesheet /path/to/timesheet.xlsx --month 2026-09"
echo ""
echo "Or start the app with a UI:"
echo "  python3 app.py    then open http://127.0.0.1:5000"
