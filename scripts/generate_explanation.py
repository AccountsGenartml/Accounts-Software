import os
from payslip import CSS, _logo

logo_src = _logo()
logo_html = f'<img src="{logo_src}" alt="Logo" onerror="this.style.display=\'none\'">' if logo_src else ''

html_content = f"""<!doctype html>
<html>
<head>
    <meta charset='utf-8'>
    <title>Salary Calculation Guide</title>
    <style>
        {{CSS}}
        @page {{ size:A4; margin:10mm; }}
        body {{
            font-size: 11px; /* Slightly larger text for readability */
            line-height: 1.6;
            color: #27272a;
        }}
        .content-body {{
            margin-top: 20px;
        }}
        h2 {{
            font-size: 14px;
            color: #18181b;
            margin-bottom: 8px;
            margin-top: 24px;
            border-bottom: 1px solid #e4e4e7;
            padding-bottom: 4px;
        }}
        p {{
            margin-bottom: 12px;
        }}
        ul {{
            margin-left: 20px;
            margin-bottom: 12px;
        }}
        li {{
            margin-bottom: 4px;
        }}
        .highlight-box {{
            background: #f4f4f5;
            border-left: 3px solid #18181b;
            padding: 12px;
            margin: 16px 0;
            border-radius: 0 4px 4px 0;
        }}
    </style>
</head>
<body>
    <div class="page">
        <!-- Header -->
        <div class="hdr">
            <div class="brand">
                {logo_html}
                <div>
                    <div class="brand-name">GENARTML PRIVATE LIMITED</div>
                    <div class="cin">AI Automation • Voice AI Agents • Workflow Intelligence</div>
                </div>
            </div>
            <div class="for-box">
                <div class="for-label">Document</div>
                <div class="for-month">Salary Calculation Guide</div>
            </div>
        </div>

        <!-- Banner -->
        <div class="banner">PAYROLL POLICIES & CALCULATION METHODOLOGY</div>

        <!-- Content -->
        <div class="content-body">
            <p><strong>Dear Genartml Team Members,</strong></p>
            <p>We understand that understanding your monthly payslip and salary calculation is important. To ensure complete transparency, this document explains how your compensation is structured and calculated each month.</p>

            <h2>1. Fixed Monthly Basic Salary & CTC Structure</h2>
            <p>Your overall Cost to Company (CTC) is divided into a fixed structure. By default, your monthly CTC is broken down as follows:</p>
            <ul>
                <li><strong>Basic Salary:</strong> 70% of your CTC</li>
                <li><strong>Fixed Allowance:</strong> 20% of your CTC</li>
                <li><strong>Performance Incentive:</strong> 10% of your CTC</li>
            </ul>
            <div class="highlight-box">
                <strong>Example:</strong> If your monthly CTC is ₹30,000, your fixed monthly Basic Salary component is ₹21,000, Fixed Allowance is ₹6,000, and Performance Incentive is ₹3,000.
            </div>

            <h2>2. Why Does the "Earned Basic Salary" Fluctuate?</h2>
            <p>You may notice slight variations in your Earned Basic Salary line item month-to-month. This component is dynamically calculated based on two main factors:</p>
            <ul>
                <li><strong>Working Days in the Month:</strong> The base per-day rate changes depending on the total number of working days in a given calendar month (excluding weekends). A month with 22 working days will have a slightly different daily rate than a month with 20 working days.</li>
                <li><strong>Adjustments (LOP and Overtime):</strong> The Basic Salary component acts as the primary adjustment line item for your final payout. Any Loss of Pay (LOP) or Overtime adjustments are factored into the Basic component before the final net pay is reached.</li>
            </ul>

            <h2>3. How is Loss of Pay (LOP) Calculated & Deducted?</h2>
            <p>Loss of Pay is calculated based on any shortfall between your total fixed CTC and your actual earned gross payout for the month, which usually corresponds to unpaid time off.</p>
            <p><strong>Deduction Method:</strong> LOP is adjusted <em>directly</em> from your Basic Salary. Instead of adding up your full fixed components and showing a separate negative deduction line item at the bottom of the payslip, the LOP amount is subtracted directly from your Basic Salary. This means your "Earned Basic Salary" line shows the amount after LOP has been removed.</p>

            <h2>4. Overtime Calculation</h2>
            <p>Overtime is calculated based on your per-hour rate (which is derived from your Basic Salary divided by the working days and standard 8-hour shifts) multiplied by 1.5x.</p>
            <p>When Overtime is paid, it is added to your total earnings as a separate "Overtime Allowance" line item.</p>

            <br><br>
            <p>We hope this clears up how your monthly payouts are structured. If you have any further questions regarding your individual payslip, please reach out to the HR / Payroll team.</p>
            
            <p>Best regards,<br>
            <strong>HR / Payroll Team</strong><br>
            Genartml Private Limited</p>
        </div>
    </div>
</body>
</html>
"""

html_content = html_content.replace("{CSS}", CSS)

with open('salary_calculation_guide.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
    
print("Generated salary_calculation_guide.html")
