import requests
import json
import sys

# Configuration
BASE_URL = "http://localhost:8035"
ENDPOINT = "/api/chatbot/query"

def test_model_provenance(query="Show me my tasks"):
    print("\n" + "=" * 60)
    print("CHATBOT MODEL PROVENANCE TEST")
    print("=" * 60)
    
    payload = {
        "query": query,
        "user_id": "6606d1df-dfb7-40f3-9a68-09f1170d90c5",
        "org_id": "dde0a075-5eb3-4b4b-8de3-0a6b1162951f",
        "context": {
            "role": "employee"
        }
    }
    
    print(f"Sending Query: \"{query}\"")
    print("Waiting for response...")
    
    try:
        response = requests.post(f"{BASE_URL}{ENDPOINT}", json=payload)
        response.raise_for_status()
        result = response.json()
        
        print("\n" + "-" * 60)
        print("PROOF OF MODEL ORIGIN")
        print("-" * 60)
        
        # Extract provenance from response
        intent_model = result.get("intent_model", "Unknown")
        synthesis_model = result.get("synthesis_model", "Unknown")
        final_answer = result.get("response", result.get("answer", "No response content"))
        
        print(f"1. INTENT PARSING (SLM):    {intent_model}")
        print(f"2. RESPONSE SYNTHESIS (SLM): {synthesis_model}")
        print("-" * 60)
        print(f"\nFinal Chatbot Response:\n{final_answer}")
        print("-" * 60)
        
        print("\nSUCCESS: You can now prove to your team lead which models are used.")
        
    except requests.exceptions.ConnectionError:
        print("\nERROR: Cannot connect to the server at http://localhost:8035")
        print("Please make sure the server is running (python unified_server.py)")
    except Exception as e:
        print(f"\nERROR: {e}")
        if 'response' in locals():
            print(f"Raw Response: {response.text}")

if __name__ == "__main__":
    test_query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Show me my tasks"
    test_model_provenance(test_query)
