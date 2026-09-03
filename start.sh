#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "Starting Genartml Payroll (Production Mode)"
echo "Available at http://127.0.0.1:5000"
python3 -m gunicorn -w 4 -b 127.0.0.1:5000 app:app
