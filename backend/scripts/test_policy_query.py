import requests
import json

url = "http://localhost:8035/orchestrate"
data = {
    "query": "What is the exit policy?",
    "user_id": "test_user_id",
    "org_id": "test_org_id",
    "context": {
        "user_role": "employee"
    }
}

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print("Response Body:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
