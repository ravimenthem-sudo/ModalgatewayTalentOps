# 🚀 Testing & Deployment Checklist (100% Accuracy)

Follow these steps to ensure the TalentOps Chatbot works with full accuracy on your local machine.

## 1. Environment Setup
- [ ] **Clone the Repository:** Ensure you have the latest code from the main branch.
- [ ] **Install Dependencies:** Run the following command in your terminal:
  ```bash
  pip install -r requirements.txt
  ```
- [ ] **Configure Environment Variables:**
  - Copy `.env.example` to a new file named `.env`.
  - Fill in your `TOGETHER_API_KEY`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`.

## 2. Database Synchronization (Supabase)
The chatbot relies on specific functions inside Supabase for semantic search.
- [ ] **Run SQL Setup:** Open your Supabase SQL Editor and execute the code found in `DATABASE_SETUP.sql`. This will create the `semantic_cache` and `chat_history` tables.

## 3. Test Data & Credentials
**CRITICAL:** The chatbot retrieves data based on who is logged in. If you use a fresh account with no tasks, the bot will correctly report "No data found."
- [ ] **Use a Demo Account:** We recommend testing with a user that already has data assigned (Tasks, Leaves, etc.).
- [ ] **Assign Sample Tasks:** If testing with a new user, manually add 2-3 tasks in the `tasks` table and assign them to that user's `user_id`.

## 4. Running the Server
- [ ] **Start Backend:** Run the following command:
  ```bash
  python unified_server.py
  ```
- [ ] **Check Port:** The server should be running on `http://localhost:8035`.

## 5. Verification Questions
Test the following to confirm accuracy:
1. "What are my pending tasks?" (Should match your dashboard)
2. "How many leaves do I have left?" (Should pull from your profile)
3. "Go to the attendance page." (Should trigger a UI redirect)
4. "What time did I start today?" (Should fetch from attendance logs)

---
**Troubleshooting:**
- If the bot gives "Hallucinations" (fictional names): Check your `.env` to ensure you are connected to the correct database.
- If the bot says "No data support": Check if `rbac_rules.py` is present in your folder.
