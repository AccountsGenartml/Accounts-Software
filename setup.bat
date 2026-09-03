@echo off
echo Genartml Payroll setup
python --version || (echo Python 3.9+ required. & exit /b 1)
python -m pip install -r requirements.txt
python test_engine.py
echo.
echo Setup complete. Run a month with:
echo   python run_payroll.py --timesheet C:\path\to\timesheet.xlsx --month 2026-09
echo.
echo Or start the app with a UI:
echo   python app.py    then open http://127.0.0.1:5000
