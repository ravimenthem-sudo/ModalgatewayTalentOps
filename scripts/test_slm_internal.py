import asyncio
import os
import sys
from dotenv import load_dotenv

# Add current directory to path
sys.path.append(os.getcwd())

load_dotenv()

from unified_server import slm_chat
from binding import SLMQueryRequest
from fastapi import BackgroundTasks

async def test_direct():
    print("Testing slm_chat directly...")
    
    # Mock BackgroundTasks
    bg = BackgroundTasks()
    
    # Test Query 1: Documents
    req1 = SLMQueryRequest(
        query="show project documents",
        user_id="00000000-0000-0000-0000-000000000000", # Guest-like but UUID
        org_id="00000000-0000-0000-0000-000000000000",
        context={"role": "manager", "app_name": "talentops"}
    )
    
    print("\n--- Testing 'show project documents' ---")
    try:
        resp1 = await slm_chat(req1, bg)
        print(f"Action: {resp1.action}")
        print(f"Response: '{resp1.response}'")
        print(f"Data: {resp1.data}")
    except Exception as e:
        print(f"Error in test1: {e}")

    # Test Query 2: Tasks
    req2 = SLMQueryRequest(
        query="open my tasks",
        user_id="00000000-0000-0000-0000-000000000000",
        org_id="00000000-0000-0000-0000-000000000000",
        context={"role": "manager", "app_name": "talentops"}
    )
    
    print("\n--- Testing 'open my tasks' ---")
    try:
        resp2 = await slm_chat(req2, bg)
        print(f"Action: {resp2.action}")
        print(f"Response: '{resp2.response}'")
        print(f"Data: {resp2.data}")
    except Exception as e:
        print(f"Error in test2: {e}")

if __name__ == "__main__":
    asyncio.run(test_direct())
