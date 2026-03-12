import requests
import json

url = "http://localhost:8035/slm/chat"
payload = {
    "query": "show my payslips",
    "user_id": "6606d1df-dfb7-40f3-8de3-0a6b1162951f",
    "org_id": "ravimenthem-sudo/ModalgatewayTalentOps",
    "user_role": "employee",
    "context": {
        "user_id": "6606d1df-dfb7-40f3-8de3-0a6b1162951f",
        "org_id": "ravimenthem-sudo/ModalgatewayTalentOps",
        "role": "employee",
        "name": "Ravindra"
    }
}

try:
    response = requests.post(url, json=payload, timeout=30)
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
