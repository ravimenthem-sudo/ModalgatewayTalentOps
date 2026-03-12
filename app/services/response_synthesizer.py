"""
app/services/response_synthesizer.py
=======================================
Layer 3: Two-phase response synthesis.
Phase 1: GPT-4o-mini generates a professional draft from data_context.
Phase 2: Llama-3.1-8B-Instruct polishes it into the final user response.

Extracted from unified_server.py (lines 1596-1736).
"""
import asyncio
import json
import logging
from typing import Dict, Any

from openai import AsyncOpenAI
from together import AsyncTogether
from app.config import OPENAI_API_KEY, TOGETHER_API_KEY, SYNTHESIS_MODEL, INTENT_MODEL

logger = logging.getLogger(__name__)
openai_client  = AsyncOpenAI(api_key=OPENAI_API_KEY)
together_client = AsyncTogether(api_key=TOGETHER_API_KEY)

# ---------------------------------------------------------------------------
# System prompt template (injected with data at runtime)
# ---------------------------------------------------------------------------
SYNTHESIS_SYSTEM_PROMPT = """You are an intelligent, data-driven HR and Workplace Assistant working within a secure, role-based enterprise application called __APP_NAME__.

Core Rules:

1. **MANDATORY MODULE IDENTIFICATION:** You MUST start your response with the exact module name and your role.
   - For Tasks -> "**Module:** My Tasks"
   - For Attendance -> "**Module:** Attendance"
   - For Leaves/Balance -> "**Module:** Leaves"
   - For Analytics -> "**Module:** Analytics"
   - For Members/Structure -> "**Module:** Organization"
   - For Policies -> "**Module:** Policies"
   - For Documents -> "**Module:** Project Documents"

   Format: "**Module:** [Name] \\n**User Role:** [Role]\\n\\n[Your response content...]"

2. Enforce Role-Based Access Control (RBAC) strictly:
   - Employees can access only their own tasks and analytics.
   - Team Leads can access their own tasks, team tasks, and team-level analytics.
   - Managers can access employee tasks and cross-team analytics.
   - Executives can access organization-level analytics only.

3. Never expose data outside the user's authorized scope.

4. If the requested information is already on the current UI page, redirect the user there instead of repeating.

5. If the information is not directly visible, provide a clear, concise summary based on the data.

6. Support simple, complex, comparative, and analytical questions for all modules (Tasks, Attendance, Leaves, Documents, Analytics).

7. **INSIGHT OVER DATA (Rule 9):** DO NOT return raw markdown tables unless explicitly requested. Summarize findings into 3–4 insightful bullet points. Explain the "why".

8. **AMBIGUITY (Rule 8):** If the query is incomplete or vague, ask a specific clarifying question. Never guess.

9. **INSUFFICIENT DATA (Rule 12):** If data is partial or null, state: "I have data for [part], but missing [part] for a full answer." Never infer missing values.

10. Always respond professionally. Use bullet points for readability.

11. **NO HALLUCINATION (Rule 14):** If DATABASE_CONTEXT is empty or shows "No records found," explicitly state the information is unavailable.

12. **STRICT DATA ADHERENCE (Rule 15):** NEVER generate fictional data, names, tasks, or projects. Only report what is explicitly in DATABASE_CONTEXT.

Your objective: Provide accurate, role-safe, insight-driven responses. Prioritize CLARIFICATION over GUESSTIMATION.

### CONTEXT FOR THIS RESPONSE
- User Role: __USER_ROLE__
- Data Quality Integrity: __DATA_INTEGRITY__
- Relevant Data Found: __DATA_CONTEXT__

### USER QUERY
__QUERY__
"""


async def synthesize_response(
    query: str,
    data_context: str,
    data_integrity: Dict,
    user_role: str,
    app_name: str = "talentops",
) -> str:
    """
    Two-phase synthesis:
      Phase 1 — GPT-4o-mini produces professional draft
      Phase 2 — Llama-3.1-8B polishes into final response
    Returns: final_response string
    """
    # Build the system prompt
    prompt = (
        SYNTHESIS_SYSTEM_PROMPT
        .replace("__APP_NAME__",     app_name.title())
        .replace("__USER_ROLE__",    str(user_role))
        .replace("__DATA_INTEGRITY__", json.dumps(data_integrity))
        .replace("__DATA_CONTEXT__", str(data_context))
        .replace("__QUERY__",        str(query))
    )

    try:
        # --- PHASE 1: Professional draft via GPT-4o-mini ---
        logger.info("🤖 Synthesizer Phase 1: GPT-4o-mini draft...")
        draft_resp = await openai_client.chat.completions.create(
            model=SYNTHESIS_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user",   "content": query},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        professional_draft = draft_resp.choices[0].message.content

        # --- PHASE 2: Polish via Llama-3.1-8B-Instruct ---
        logger.info("✨ Synthesizer Phase 2: Llama-3.1-8B polish...")
        slm_prompt = (
            f"You are a professional HR assistant. Below is a professional draft response based "
            f"on the latest database information. Your job is to read this draft and provide the "
            f"FINAL response to the user. Maintain the professional tone and preserve module info.\n\n"
            f"DRAFT RESPONSE:\n{professional_draft}\n\n"
            f"USER QUERY:\n{query}\n\n"
            f"Provide the FINAL response below:"
        )
        final_completion = await together_client.chat.completions.create(
            model=INTENT_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional workplace assistant."},
                {"role": "user",   "content": slm_prompt},
            ],
            temperature=0.0,
            max_tokens=400,
        )
        if asyncio.iscoroutine(final_completion):
            final_completion = await final_completion

        return final_completion.choices[0].message.content

    except Exception as e:
        logger.error(f"Response Synthesizer Error: {e}")
        # Graceful fallback — return the raw data context
        if data_context and "No" not in data_context[:20]:
            return f"Based on the data I found:\n\n{data_context[:500]}"
        return "I encountered an issue processing your request. Please try again or rephrase your question."
