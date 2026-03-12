import os
import json
from supabase import create_client
from dotenv import load_dotenv

# Load .env file
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY')

s = create_client(url, key)

print("--- PROFILES containing 'Ravindra' ---")
try:
    p_data = s.table('profiles').select('id, full_name').ilike('full_name', '%Ravindra%').execute()
    print(json.dumps(p_data.data, indent=2))
    
    if p_data.data:
        user_id = p_data.data[0]['id']
        print(f"\n--- TASKS for user_id: {user_id} ---")
        t_data = s.table('tasks').select('title, priority, status, assigned_to').eq('assigned_to', user_id).execute()
        print(json.dumps(t_data.data, indent=2))
    else:
        print("No profile found for Ravindra")
except Exception as e:
    print(f"Error: {e}")
