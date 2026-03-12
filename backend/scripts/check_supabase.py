import os
import requests
from dotenv import load_dotenv

load_dotenv()

def check_table(table_name):
    url = os.getenv("TALENTOPS_SUPABASE_URL")
    key = os.getenv("TALENTOPS_SUPABASE_SERVICE_ROLE_KEY")
    full_url = f"{url}/rest/v1/{table_name}?select=id,title"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}"
    }
    try:
        r = requests.get(full_url, headers=headers)
        if r.status_code == 200:
            data = r.json()
            print(f"Table '{table_name}' has {len(data)} records.")
            for item in data[:5]:
                print(f"  - {item.get('title')} ({item.get('id')})")
        else:
            print(f"Error checking '{table_name}': {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Exception checking '{table_name}': {e}")

if __name__ == "__main__":
    check_table("documents")
    check_table("project_documents")
    check_table("tasks")
