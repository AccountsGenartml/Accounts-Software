import json
import io
import re
from decimal import Decimal
import datetime as dt
import google.generativeai as genai
from engine import money

# System prompt to guide the LLM to extract exactly what we need
SYS_PROMPT = """You are a precise payroll extraction assistant.
You will be given the raw text extracted from a PDF Payroll Computation Report.
Your task is to extract the exact numerical values for each employee for the month.

The output MUST be a valid JSON array of objects. Do not include any markdown formatting like ```json or anything else. Just the raw JSON array.
Each object must represent one employee and have the following exact schema:
{
  "name": "Employee Full Name",
  "base_salary": 21000.00,
  "incentive": 3000.00,
  "allowance": 3000.00,
  "ot_payable": 0.00,  # The money amount paid for overtime, 0 if none
  "ot_hours": 0.00, # The number of hours of OT, 0 if none or not stated
  "lop_deduction": 4000.00, # Money deducted for LWP or Leave Without Pay, 0 if none
  "lop_days": 4, # Number of days deducted for LWP, 0 if none or not stated
  "partial_day_deduction": 1000.00, # Money deducted for Half Days, late marks, or shortfalls
  "professional_tax": 200.00, # 0 if none
  "gross": 27450.00,
  "net_pay": 21750.00
}

Instructions:
1. Strip all currency symbols (₹, $) and commas from numbers. Output raw floats.
2. If a field is missing or not applicable for an employee, output 0.00.
3. Be careful to sum up all LWP and Half Day/WFH deductions properly if they are listed separately under deductions. Put Leave Without Pay money under 'lop_deduction', and Half Day / Work From Home deductions under 'partial_day_deduction'.
4. Ensure the math balances out according to the PDF.
"""

def extract_payroll_from_pdf(pdf_bytes, api_key):
    genai.configure(api_key=api_key)
    
    # 1. Provide PDF natively (handles scanned images & raw text instantly)
    doc_part = {
        "mime_type": "application/pdf",
        "data": pdf_bytes
    }
    
    # 2. Call Gemini API
    models_to_try = [
        'gemini-3.0-pro',
        'gemini-3.0-flash',
        'gemini-2.5-pro',
        'gemini-2.5-flash',
        'gemini-1.5-pro',
        'gemini-1.5-flash',
        'gemini-1.0-pro',
        'gemini-pro',
        'gemini-1.0-pro-latest'
    ]
    
    response = None
    last_error = None
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                [SYS_PROMPT + "\n\nEXTRACT FROM THE FOLLOWING TIMESHEET DOCUMENT:\n", doc_part],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            break
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if "404" in err_str or "not found" in err_str or "not supported" in err_str:
                continue
            else:
                raise e
                
    if not response:
        raise Exception(f"All Gemini models failed. Last error: {str(last_error)}")
    
    # 3. Parse JSON (cleaning any markdown tags just in case)
    try:
        raw = response.text.strip()
        if raw.startswith("```json"): raw = raw[7:]
        elif raw.startswith("```"): raw = raw[3:]
        if raw.endswith("```"): raw = raw[:-3]
        
        data = json.loads(raw.strip())
        if not isinstance(data, list):
            data = [data] # Ensure array
        return data
    except Exception as e:
        raise ValueError(f"Failed to parse AI output: {e}\nRaw output: {response.text}")

def convert_to_standard_results(ai_data, year, month, master_employees):
    """Converts the flat AI JSON into the complex dict needed by payslip.py & app.py"""
    results = []
    
    # Find active paid days for standard reference
    pd = 20 # Fallback 
    
    for emp_data in ai_data:
        name = emp_data.get("name", "Unknown")
        
        # Match with master employee database to get static info (CTC, ID, etc)
        master_emp = next((e for e in master_employees if e["name"].lower() == name.lower()), None)
        
        if not master_emp:
            # Fallback if employee isn't in database, create a dummy
            master_emp = {
                "name": name,
                "emp_id": f"TEMP-{name[:3].upper()}",
                "ctc_monthly": float((emp_data.get("base_salary", 0) / 0.7)) if emp_data.get("base_salary", 0) > 0 else 0
            }
            
        base = money(emp_data.get("base_salary", 0))
        allowance = money(emp_data.get("allowance", 0))
        incentive = money(emp_data.get("incentive", 0))
        ot_payable = money(emp_data.get("ot_payable", 0))
        ot_hours = money(emp_data.get("ot_hours", 0))
        
        gross = money(emp_data.get("gross", 0))
        ptax = money(emp_data.get("professional_tax", 0))
        lop_deduction = money(emp_data.get("lop_deduction", 0))
        partial_deduction = money(emp_data.get("partial_day_deduction", 0))
        
        total_deductions = ptax + lop_deduction + partial_deduction
        net = money(emp_data.get("net_pay", 0))
        
        # Construct the standard result payload
        res = {
            "employee": master_emp,
            "rows_in_month": 0, # AI run doesn't have timesheet rows
            "paid_days": pd,
            "active_paid_days": pd,
            "month_fraction": 1.0,
            "payable_days": pd - float(emp_data.get("lop_days", 0)),
            "lop_days": float(emp_data.get("lop_days", 0)),
            "type_counts": {},
            "leave_availed": {"CL": 0, "SL": 0, "EL": 0},
            "base_salary": base,
            "per_day": money(0), # Not derivable reliably from just the PDF
            "per_hour": money(0),
            "ot_rate": money(0),
            "ot_hours": float(ot_hours),
            "base_earned": base, # Static base!
            "ot_payable": ot_payable,
            "allowance_full": allowance,
            "incentive_full": incentive,
            "allowance_paid": allowance,
            "incentive_paid": incentive,
            "lop_deduction": lop_deduction,
            "partial_day_deduction": partial_deduction,
            "gross": gross,
            "professional_tax": ptax,
            "other_deductions": money(0),
            "total_deductions": total_deductions,
            "reimbursements": money(0),
            "net_pay": net,
            "flags": [{"code": "AI_GENERATED", "detail": "This payslip was generated directly from an AI PDF scan. Please verify the amounts."}]
        }
        results.append(res)
        
    return results
