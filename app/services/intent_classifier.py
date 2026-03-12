"""
app/services/intent_classifier.py
===================================
Layer 2: LLM-driven intent classification.
Takes a user query + conversation history and returns:
  { action, params, confidence, is_ambiguous, reasoning }

Extracted from unified_server.py (lines 477-623).
"""
import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Tuple

from together import AsyncTogether
from app.config import TOGETHER_API_KEY, INTENT_MODEL

logger = logging.getLogger(__name__)
together_client = AsyncTogether(api_key=TOGETHER_API_KEY)


async def classify_intent(
    query: str,
    system_prompt: str,
    history: List[Dict] = None,
) -> Tuple[str, Dict, int, bool, str]:
    """
    Calls the Together AI 8B model to classify user intent.

    Returns:
        (action, params, confidence, is_ambiguous, reasoning)
    """
    history = history or []
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": query},
    ]

    try:
        response = await together_client.chat.completions.create(
            model=INTENT_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=256,
            timeout=10,
        )
        if asyncio.iscoroutine(response):
            response = await response

        ai_text = response.choices[0].message.content
        json_match = re.search(r"\{.*\}", ai_text, re.DOTALL)

        if json_match:
            intent = json.loads(json_match.group())
            action       = intent.get("action", "chat")
            params       = {k.lower(): v for k, v in intent.get("parameters", {}).items()}
            confidence   = intent.get("confidence", 100)
            is_ambiguous = intent.get("is_ambiguous", False)
            reasoning    = intent.get("reasoning", "")
            logger.info(f"🧠 Intent: {action} | Confidence: {confidence}% | Reasoning: {reasoning}")
            return action, params, confidence, is_ambiguous, reasoning
        else:
            logger.warning("⚠️ No JSON in LLM response — defaulting to chat")
            return "chat", {}, 0, False, "No JSON found"

    except Exception as e:
        logger.error(f"Intent Classifier Error: {e}")
        return "chat", {}, 0, False, str(e)


def build_system_prompt(
    app_name: str,
    user_role: str,
    current_route: str,
    action_schemas_str: str,
    nav_rules: Dict,
) -> str:
    """Builds the intent classifier system prompt with role + nav context."""
    return f"""You are a professional workplace assistant for {app_name.title()}.
Your primary goal is to parse user intents into actions.

CURRENT CONTEXT:
- User Role: {user_role}
- Current UI Page: {current_route}

INSTRUCTIONS:
1. **REASONING FIRST:** Determine if the user wants to SEE info (fetch) or GO to a page (navigate).
2. **MUTATIONS ALWAYS WIN:** Instructions for data changes (approve, clock, apply) MUST use the specific functional action.
3. **DATA RETRIEVAL (DEFAULT):** For queries starting with "show me", "what are", "list", or "get", ALWAYS use a data-fetching action.
4. **NAVIGATION (STRICT):** ONLY use `navigate_to_module` if the user says "go to [X] page", "open [X] module", or "take me to [X]".
5. **MANDATORY:** Never use `navigate_to_module` for 'notifications' or 'documents' unless the word 'page' or 'module' is explicitly used.

ACTION SCHEMAS:
{action_schemas_str}
- "navigate_to_module": {{"module": "name", "route": "url"}} (Routes: {json.dumps(nav_rules)})

Return ONLY JSON:
{{
    "reasoning": "Briefly state why you chose this action.",
    "action": "action_name",
    "confidence": 0-100,
    "parameters": {{ "key": "value" }},
    "is_ambiguous": true/false
}}

STRICT RULE: NEVER provide data or examples in this phase. Only identify the action.
"""


def build_nav_rules(norm_role: str, prefix: str) -> Dict[str, str]:
    """Returns the navigation URL map for a given role."""
    if norm_role == "employee":
        return {
            "dashboard":          f"{prefix}dashboard",
            "tasks_page":         f"{prefix}my-tasks",
            "attendance_page":    f"{prefix}team-status",
            "leaves_page":        f"{prefix}leaves",
            "team_members_page":  f"{prefix}employees",
            "analytics_page":     f"{prefix}analytics",
            "notifications_page": f"{prefix}notifications",
            "documents_page":     f"{prefix}documents",
            "payslips_page":      f"{prefix}payslips",
            "policies_page":      f"{prefix}policies",
            "announcements_page": f"{prefix}announcements",
        }
    else:
        rules = {
            "dashboard":          f"{prefix}dashboard",
            "tasks_page":         f"{prefix}tasks",
            "attendance_page":    f"{prefix}employee-status",
            "leaves_page":        f"{prefix}leaves",
            "team_members_page":  f"{prefix}employees",
            "analytics_page":     f"{prefix}analytics",
            "notifications_page": f"{prefix}notifications",
            "documents_page":     f"{prefix}documents",
            "payslips_page":      f"{prefix}payslips",
        }
        if norm_role in ["manager", "executive"]:
            rules["hiring_portal"]    = f"{prefix}hiring"
            rules["project_mgmt"]     = f"{prefix}project-management" if norm_role == "executive" else f"{prefix}project-members"
        if norm_role == "manager":
            rules["my_leaves"]        = f"{prefix}my-leaves"
        return rules


def get_role_prefix(norm_role: str, app_name: str) -> str:
    """Returns the URL prefix for a given role."""
    if app_name == "cohort":
        return "/student-dashboard/"
    if norm_role == "executive":
        return "/executive-dashboard/"
    elif norm_role == "manager":
        return "/"
    elif norm_role in ["team_lead", "teamlead"]:
        return "/"
    else:
        return "/employee-dashboard/"
