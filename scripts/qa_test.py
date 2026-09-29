import requests
import json
url = "http://127.0.0.1:5000/api/expenses"
data = {"spent_on": "2026-08-16", "category": "Office & supplies", "vendor": "Stationery Store", "description": "Pens and paper", "amount": 1500}
files = {"file": ("test_invoice.txt", b"dummy invoice data")}
response = requests.post(url, data={"data": json.dumps(data)}, files=files)
print(response.json())
