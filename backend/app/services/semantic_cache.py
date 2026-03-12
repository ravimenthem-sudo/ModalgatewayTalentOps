"""
app/services/semantic_cache.py
================================
Semantic cache helpers — check and save high-quality query-response pairs.
Extracted from unified_server.py (lines 289-371).
"""
import asyncio
import logging
from typing import Optional

from binding import supabase, get_embeddings

logger = logging.getLogger(__name__)

# Keywords that signal dynamic/personal data — always bypass cache
DYNAMIC_BYPASS_KEYWORDS = [
    "task", "attendance", "leave", "notification", "clock",
    "hiring", "candidate", "analytics", "project member", "my "
]


async def check_semantic_cache(query: str, org_id: str, user_id: str, project_id: str = None) -> Optional[str]:
    """Check semantic cache for a similar query. Returns cached response or None."""
    try:
        q_lower = query.lower()
        if any(k in q_lower for k in DYNAMIC_BYPASS_KEYWORDS):
            logger.info(f"⏩ CACHE BYPASS: Dynamic query — '{query}'")
            return None

        q_emb, _ = await get_embeddings([query])
        if not q_emb:
            return None

        params = {
            "query_embedding": q_emb[0],
            "match_threshold": 0.96,
            "match_count": 1,
            "msg_org_id": org_id,
            "msg_user_id": user_id,
            "msg_project_id": project_id
        }
        resp = await supabase.rpc("match_semantic_cache", params)
        if resp.data and len(resp.data) > 0:
            match = resp.data[0]
            logger.info(f"🚀 CACHE HIT: Similarity {match['similarity']:.4f}")
            return match["response_text"]
        return None
    except Exception as e:
        logger.error(f"Semantic Cache Lookup Error: {e}")
        return None


async def save_semantic_cache(
    query: str, response: str, org_id: str,
    user_id: str, user_role: str, project_id: str = None
):
    """Save a successful query-response pair to semantic cache."""
    try:
        if any(x in response for x in ["ERROR:", "Redirecting", "not quite sure", "Could you please clarify"]):
            return

        personal_keywords = ["my", "me", "i ", "i'm", "own"]
        is_personal = any(k in query.lower() for k in personal_keywords)
        save_user_id = user_id if is_personal else None

        q_emb_res = await get_embeddings([query])
        q_emb, _ = q_emb_res if isinstance(q_emb_res, tuple) else (q_emb_res, 0)
        if not q_emb:
            return

        await supabase.table("semantic_cache").insert({
            "query_text": query,
            "query_embedding": q_emb[0],
            "response_text": response,
            "org_id": org_id,
            "project_id": project_id,
            "user_id": save_user_id,
            "user_role": user_role
        }).execute()
        logger.info("💾 Saved to semantic cache.")
    except Exception as e:
        logger.error(f"Semantic Cache Storage Error: {e}")
