import requests
import json

URL = "http://localhost:8035/slm/chat"

def test_query(query, user_id="849da103-9dcd-4277-96a8-f716912368cc"):
    payload = {
        "query": query,
        "user_id": user_id,
        "org_id": "849da103-9dcd-4277-96a8-f716912368cc",
        "app_name": "talentops",
        "user_role": "Employee",
        "context": {"route": "/employee-dashboard/dashboard"}
    }
    
    print(f"\nUser Query: {query}")
    try:
        response = requests.post(URL, json=payload)
        res_json = response.json()
        full_res = res_json.get('response')
        print(f"Chatbot Response Sample:\n{full_res[:400]}...") 
        print(f"Action: {res_json.get('action')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test 1: Attendance
    test_query("What time did I start today?")
    
    # Test 2: Leaves
    test_query("How many casual leaves do I have left?")
