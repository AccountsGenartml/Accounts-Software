@echo off
cd /d "%~dp0"
echo Starting Genartml Payroll (Production Mode)
echo Available at http://127.0.0.1:5000
waitress-serve --port=5000 app:app
pause
