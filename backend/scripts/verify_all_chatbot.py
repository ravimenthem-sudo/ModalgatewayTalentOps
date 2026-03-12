import requests
import json

url = "http://localhost:8035/slm/chat"

def test_query(query, name="Test"):
    payload = {
        "query": query,
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
    print(f"\n--- Testing: {query} ---")
    try:
        response = requests.post(url, json=payload, timeout=60)
        print(f"Status: {response.status_code}")
        print(response.json().get("response", "No response field"))
    except Exception as e:
        print(f"Error: {e}")

# Test all 3 problematic modules
test_query("show my payslips")
test_query("check my leave balance")
test_query("show organization hierarchy")
