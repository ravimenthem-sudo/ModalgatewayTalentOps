"""
Unified Modal Gateway Server
Combines SLM, LLM (OpenAI), and RAG backends into a single FastAPI application.
All routes available at the root level - no mounting needed.
Runs on port 8035.
"""

import uvicorn
import datetime as dt
import time
import os
import sys
import json
import re
import asyncio
from contextvars import ContextVar
from dotenv import load_dotenv
from app.rbac_rules import check_permission, ACTION_REGISTRY, get_role_level

# Load environment variables FIRST
load_dotenv()

# Set working directory to the script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from typing import Optional, Dict, Any, List
import json
import re
import httpx
import redis.asyncio as redis
from pydantic import BaseModel

# Import binding library
from binding import (
    supabase, 
    select_client, 
    init_db, 
    init_rag,
    SLMQueryRequest,
    SLMQueryResponse,
    LLMQueryRequest,
    LLMQueryResponse,
    OrchestratorRequest,
    RAGIngestRequest,
    RAGQueryRequest,
    chunk_text,
    get_embeddings,
    parse_file_from_url
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import io
import PyPDF2
try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

# =============================================================================
# CONFIGURATION — now centralized in app/config.py
# =============================================================================
from app.config import (
    TOGETHER_API_KEY, OPENAI_API_KEY,
    TALENTOPS_SUPABASE_URL, TALENTOPS_SERVICE_ROLE_KEY,
    COHORT_SUPABASE_URL, COHORT_SERVICE_ROLE_KEY,
    REDIS_URL, PORT,
)

# Initialize external clients
from together import AsyncTogether
from openai import AsyncOpenAI
import redis.asyncio as redis

together_client = AsyncTogether(api_key=TOGETHER_API_KEY)
openai_client   = AsyncOpenAI(api_key=OPENAI_API_KEY)
redis_client    = redis.from_url(REDIS_URL, decode_responses=True)

# =============================================================================
# PRODUCTION UTILITIES — now in app/state.py
# =============================================================================
from app.state import (
    TokenBucketRateLimiter,
    RedisSharedState,
    SupabaseSharedState,
    get_shared_state,
    get_shared_state_singleton,
    redis_client as _state_redis,
)

# Initialize rate limiter (fails open if Redis unavailable)
rate_limiter = TokenBucketRateLimiter(_state_redis, capacity=10, refill_rate=0.5)

def log_latency(model_type, ttft, total_latency, generation_latency, tokens_generated, status="success", **kwargs):
    """Structured JSON logging for production observability (Phase 2.3)."""
    try:
        tokens_per_second = tokens_generated / generation_latency if generation_latency > 0 else 0
        log_entry = {
            "timestamp": dt.datetime.now().isoformat(),
            "model": model_type,
            "latency_total_s": round(total_latency, 3),
            "latency_ttft_s": round(ttft, 3),
            "latency_gen_s": round(generation_latency, 3),
            "tps": round(tokens_per_second, 2),
            "tokens": tokens_generated,
            "status": status
        }
        log_entry.update(kwargs)
        
        # Structured JSON Output for Cloud Logging (Datadog/CloudWatch/Kibana)
        print(json.dumps(log_entry))
        
        # Friendly Human-Readable Log (Phase 2.3)
        logger.info(f"⏱️ [{model_type}] Processing Complete: Total={log_entry['latency_total_s']}s | TTFT={log_entry['latency_ttft_s']}s | Status={status}")
        
        # Backwards compatible file logging
        with open("audit_logs.json", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
            
    except Exception as e:
        logger.error(f"Structured Logging Error: {e}")

# =============================================================================
# INITIALIZE BINDING LAYER (Passive Model)
# =============================================================================
init_db(
    TALENTOPS_SUPABASE_URL, 
    TALENTOPS_SERVICE_ROLE_KEY, 
    COHORT_SUPABASE_URL, 
    COHORT_SERVICE_ROLE_KEY
)
init_rag(openai_client)

# =============================================================================
# MAIN APP
# =============================================================================
app = FastAPI(title="Modal Gateway - Unified Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# SEMANTIC CACHE HELPERS — now in app/services/semantic_cache.py
# =============================================================================
from app.services.semantic_cache import check_semantic_cache, save_semantic_cache

# =============================================================================
# SERVICE MODULES — intent classification, mutations, synthesis
# =============================================================================
from app.services.intent_classifier import (
    classify_intent, build_system_prompt, build_nav_rules, get_role_prefix
)
from app.services.mutations import handle_mutation
from app.services.response_synthesizer import synthesize_response

# =============================================================================
# HEALTH ENDPOINTS
# =============================================================================
@app.get("/")
async def root():
    return {"message": "Modal Gateway - Unified Server", "status": "running", "port": PORT}

@app.get("/health")
async def health():
    return {"status": "ok", "services": ["slm", "llm", "rag"]}

@app.get("/slm/health")
async def slm_health():
    return {"status": "ok", "service": "SLM Backend"}

@app.get("/llm/health")
async def llm_health():
    return {"status": "ok", "service": "LLM Backend (OpenAI)"}

@app.get("/rag/health")
async def rag_health():
    return {"status": "ok", "service": "RAG Backend"}

# Infra classes (SimpleSupabaseClient, SupabaseProxy, select_client, etc.) 
# and DTO models (SLMQueryRequest, SLMQueryResponse) have been extracted 
# to the 'binding' library.

@app.post("/slm/chat")
async def slm_chat(request: SLMQueryRequest, background_tasks: BackgroundTasks):
    """Main SLM chatbot endpoint"""
    total_start = time.perf_counter()
    rag_metrics = {"embedding_latency": 0.0, "retrieval_latency": 0.0}
    is_rag_triggered = False
    try:
        query = request.query
        user_id = request.user_id
        org_id = request.org_id
        project_id = request.project_id
        team_id = request.team_id
        user_role = request.user_role or "consultant"
        app_name = (request.app_name or "talentops").lower()

        # --- 📍 LAYER 0: CONTEXT EXTRACTION (Absolute Security) ---
        # We extract this first so that ALL logic has access to user/org IDs.
        if request.context:
             if not user_id: user_id = request.context.get("user_id")
             if not org_id: org_id = request.context.get("org_id")
             if not project_id: project_id = request.context.get("project_id")
             if not team_id: team_id = request.context.get("team_id")
             if not user_role: user_role = request.context.get("role") or "consultant"
             if not request.app_name: 
                 app_name = (request.context.get("app_name") or "talentops").lower()
                 request.app_name = app_name
             else:
                 app_name = request.app_name.lower()
        else:
            app_name = (request.app_name or "talentops").lower()

        # --- DB CONTEXT SWITCHING (FIX 3: centralized via select_client) ---
        _client_error = select_client(app_name)
        if _client_error == "COHORT_UNAVAILABLE":
            return SLMQueryResponse(
                response="The Cohort service is not currently available. Please contact your administrator.",
                action="error",
                data={}
            )

        # --- 🚀 LAYER 0.2: RATE LIMITING (Phase 2.3) ---
        if not await rate_limiter.consume(f"user:{user_id}"):
            return SLMQueryResponse(
                response="System is currently under high load. Please wait a moment before your next request.",
                action="rate_limit",
                data={"retry_after": 2}
            )

        # --- 🚀 LAYER 0.5: SEMANTIC CACHE CHECK ---
        # Note: Moved to orchestrate_query for speed.

        # --- RAG DETECTION (@mention or Keywords) ---
        is_rag_query = "@" in query or any(k in query.lower() for k in RAG_KEYWORDS)
        
        # Bypass RAG if it's a simple list/show documents request (SLM is better for listing)
        if any(x in query.lower() for x in ["list documents", "show documents", "get documents", "list project documents", "show project documents", "available documents", "what documents"]):
            is_rag_query = False
            
        if is_rag_query and not request.forced_action:
            logger.info("🔒 RAG DETECTED: Fetching document content...")
            rag_req = RAGQueryRequest(
                question=query,
                org_id=org_id or request.org_id,
                project_id=project_id or request.project_id,
                app_name=app_name
            )
            rag_resp = await rag_query(rag_req)
            is_rag_triggered = True
            rag_metrics = rag_resp.get("metrics", rag_metrics)
            if rag_resp.get("answer"):
                request.forced_action = "present_rag"
                request.rag_content = rag_resp.get("answer")
                request.rag_source = ", ".join(rag_resp.get("sources", [])) if rag_resp.get("sources") else "Database"
                # Clean @mentions from query for the final synthesis
                query = re.sub(r'@[a-zA-Z0-9_]+', '', query).strip()
                request.query = query

        # --- LLM-DRIVEN INTENT CLASSIFICATION ---
        # Everything now goes through the LLM for maximum accuracy and rule compliance.
        action = request.forced_action
        params = request.pending_params or {}
        confidence = 100
        direct_response = None
        is_ambiguous = False

        # Determine dashboard prefix and navigation rules based on role and app
        norm_role = user_role.lower().replace(" ", "_")
        prefix = "/employee-dashboard/"
        if app_name == "cohort":
            prefix = "/student-dashboard/"
        if norm_role == "executive":
            prefix = "/executive-dashboard/"
        elif norm_role == "manager":
            prefix = "/manager-dashboard/"
        elif norm_role == "team_lead" or norm_role == "teamlead":
            prefix = "/teamlead-dashboard/"

        # Define navigation rules for the LLM and the redirect resolver
        if norm_role == "employee":
            nav_rules = {
                "dashboard": f"{prefix}dashboard",
                "tasks_page": f"{prefix}my-tasks",
                "attendance_page": f"{prefix}team-status",
                "leaves_page": f"{prefix}leaves",
                "project_page": f"{prefix}employees",
                "team_members_page": f"{prefix}team-members",
                "analytics_page": f"{prefix}analytics",
                "notifications_page": f"{prefix}notifications",
                "documents_page": f"{prefix}employees"
            }
        elif norm_role == "manager":
            nav_rules = {
                "dashboard": f"{prefix}dashboard",
                "tasks_page": f"{prefix}tasks",
                "attendance_page": f"{prefix}attendance-logs",
                "leaves_page": f"{prefix}leaves",
                "project_page": f"{prefix}documents",
                "team_members_page": f"{prefix}project-members",
                "analytics_page": f"{prefix}analytics",
                "notifications_page": f"{prefix}notifications",
                "documents_page": f"{prefix}documents",
                "my_leaves": f"{prefix}my-leaves",
                "hiring_portal": f"{prefix}hiring"
            }
        elif norm_role == "team_lead":
            nav_rules = {
                "dashboard": f"{prefix}dashboard",
                "tasks_page": f"{prefix}tasks",
                "attendance_page": f"{prefix}team-status",
                "leaves_page": f"{prefix}leaves",
                "project_page": f"{prefix}project",
                "team_members_page": f"{prefix}employees",
                "analytics_page": f"{prefix}analytics",
                "notifications_page": f"{prefix}notifications",
                "documents_page": f"{prefix}project"
            }
        elif norm_role == "executive":
            nav_rules = {
                "dashboard": f"{prefix}dashboard",
                "tasks_page": f"{prefix}tasks",
                "attendance_page": f"{prefix}attendance-logs",
                "leaves_page": f"{prefix}leaves",
                "project_page": f"{prefix}documents",
                "employees_page": f"{prefix}employees",
                "analytics_page": f"{prefix}analytics",
                "notifications_page": f"{prefix}notifications",
                "documents_page": f"{prefix}documents"
            }
        else:
            # Default fallback
            nav_rules = {
                "dashboard": f"{prefix}dashboard",
                "documents_page": f"{prefix}employees"
            }

        if not action:

            # PHASE 2: INTENT CLASSIFICATION (Centralized Service)
            try:
                # Retrieve last 4 messages so the AI understands follow-up questions
                try:
                    _shared = await get_shared_state_singleton()
                    _session_id = request.context.get("session_id", user_id) if request.context else user_id
                    _history = await _shared.get_history(_session_id, user_id, org_id, limit=4)
                except Exception:
                    _history = []

                # Build nav rules and system prompt via centralized services
                norm_role = user_role.lower().replace(" ", "_")
                prefix = get_role_prefix(norm_role, app_name)
                nav_rules = build_nav_rules(norm_role, prefix)
                
                # Fetch Action Schemas from Registry
                action_schemas_list = []
                for act_name, act_info in ACTION_REGISTRY.items():
                    schema = f'- "{act_name}": {json.dumps(act_info["parameters"])}'
                    if act_name == "navigate_to_module":
                        schema = f'- "navigate_to_module": {{"module": "name", "route": "url"}} (Routes: {json.dumps(nav_rules)})'
                    action_schemas_list.append(schema)
                action_schemas_str = "\n        ".join(action_schemas_list)

                current_route = (request.context.get("route", "Unknown")) if request.context else "Unknown"
                system_prompt = build_system_prompt(app_name, user_role, current_route, action_schemas_str, nav_rules)

                # Call the centralized intent classifier service
                action, params, confidence, is_ambiguous, reasoning = await classify_intent(
                    query, 
                    system_prompt, 
                    _history
                )
                
                logger.info(f"🧠 Centralized Intent: {action} | Confidence: {confidence}%")
                
            except Exception as e:
                logger.error(f"Error in Intent Classification Service: {e}")
                action = "chat"
                params = {}
                confidence = 0
                is_ambiguous = False


        # --- AMBIGUITY & CONFIDENCE (Rule 8) ---
        # "Analyze my status" or vague terms trigger this.
        if (is_ambiguous or confidence < 75) and action != "greeting":
            logger.info(f"🛡️ AMBIGUITY DETECTED: Confidence {confidence}%")
            if "status" in query.lower():
                 return SLMQueryResponse(
                    response="I can certainly analyze your status for you. To be helpful, would you like me to check your **Tasks**, your **Attendance**, or your **Leave Balance**?",
                    action="chat",
                    data={"clarification_for": "status"}
                )
            
            # --- RULE 8 & 11 STRICT ENFORCEMENT ---
            return SLMQueryResponse(
                response="I'm not quite sure I understood that correctly. Could you please clarify what you'd like me to do? (e.g. check tasks, mark attendance, or list documents)",
                action="ask_clarification",
                data={}
            )

        # 5. Handle LLM-driven Navigation (Rule 4 & General Redirection)
        if action == "navigate_to_module":
            logger.info(f"📍 LLM-DRIVEN NAVIGATION: {params}")
            
            # Auto-resolve route if only module is provided (robustness fix)
            module = params.get("module", "")
            route = params.get("route", "")
            if module and not route:
                route = nav_rules.get(module, "")
                logger.info(f"🔄 Auto-resolved route for {module}: {route}")
            elif route and not module:
                # Reverse lookup if needed
                for mod, url in nav_rules.items():
                    if url == route:
                        module = mod
                        break
            
            msg = direct_response or "Redirecting you now..."
            if params.get("already_here"):
                msg = f"You're already on that page! The information you're looking for should be visible right here."
            
            # --- STRICT RULE 4 ENFORCEMENT ---
            current_route = request.context.get("route", "") if request.context else ""
            if (route and current_route and route.strip('/') == current_route.strip('/')) or params.get("already_here"):
                logger.info(f"🛡️ RULE 4 INTERCEPT: User is already on {current_route}. Blocking navigation.")
                return SLMQueryResponse(
                    response="The information you are looking for is already visible on your current page.",
                    action="chat",
                    data={"rule_4_intercept": True}
                )
            
            return SLMQueryResponse(
                response=msg,
                action="navigate_to_module",
                data={
                    "route": route,
                    "module": module,
                    "already_here": params.get("already_here", False)
                }
            )

        # --- AMBIGUITY & CONFIDENCE (Rule 8) ---

        # --- 0. AMBIGUITY \u0026 COMPLETENESS CHECK (Rules 8 \u0026 12) ---
        # If the query is analytical but missing dimensions, ask for them now.
        analytical_intents = ["get_tasks", "get_attendance", "get_leave_balance", "get_hiring_overview"]
        if action in analytical_intents:
            # Check for missing time ranges if it's a trend question
            trend_keywords = ["trend", "history", "analytics", "over time", "performance", "pattern"]
            is_trend_query = any(k in query.lower() for k in trend_keywords)
            
            # If it's a trend query but no time-related parameters are in the query
            time_indicators = ["month", "week", "year", "since", "from", "today", "yesterday", "january", "february", "march", "last"]
            has_time = any(t in query.lower() for (t) in time_indicators)
            
            if is_trend_query and not has_time:
                return SLMQueryResponse(
                    response="I can certainly analyze that for you. To give you an accurate trend or insight, could you please specify the **time period** (e.g., 'this month', 'last 30 days', or 'since January')?",
                    action="chat",
                    data={"context_needed": "time_range"}
                )

        data_context = ""
        # Metadata tracker for Rule 12 compliance
        data_integrity = {"status": "success", "completeness": "full", "count": 0}
        
        # --- REAL DATABASE ACTIONS (MUTATIONS - Centralized Service) ---
        mutations = [
            "clock_in", "clock_out", "apply_leave", "approve_leave", "reject_leave", 
            "post_announcement", "create_event", "update_event", "delete_event",
            "assign_task", "update_task_status"
        ]
        
        if action in mutations:
            # Delegate all database writes to the mutations service
            data_context = await handle_mutation(action, params, request, user_id, org_id, project_id)


        # --- DATA FETCHING (Enhanced for ALL Roles) ---
        elif action == "get_tasks":
            try:
                # Use wildcard to be resilient to different schemas (TalentOps vs Cohort)
                # Still join projects for project names
                t_query = supabase.table("tasks").select("*, projects(name)")
                
                # Identify if the user is asking about themselves vs the team
                team_triggers = ["team", "everyone", "all employees", "all workers", "project tasks", "member tasks", "tasks of", "task of", "assigned to", "who is working on"]
                is_personal_query = any(w in query.lower() for w in ["my", " me", " i "])
                is_team_intent = any(w in query.lower() for w in team_triggers)
                
                # Role-based restriction: Managers, Team Leads, and Executives can see team data
                privileged_roles = ["executive", "manager", "team_lead", "admin"]
                is_privileged = request.user_role.lower() in privileged_roles
                
                # RULE 2 ENHANCEMENT: Explicit denial for employees requesting team data
                if is_team_intent and not is_privileged:
                    logger.info(f"🚫 RBAC BLOCK: Employee {user_id} attempted to access team tasks")
                    data_context = "As an Employee, you can only view your own tasks. Team tasks are accessible to Team Leads, Managers, and Executives. If you need information about team progress, please contact your Team Lead or Manager."
                elif is_personal_query or not is_privileged:
                    # STRICT FILTER: Show only the current user's tasks
                    logger.info(f"📍 FILTERING: Showing personal tasks for user_id: {user_id}")
                    t_query = t_query.eq("assigned_to", user_id)
                elif is_team_intent and is_privileged:
                    # ALLOW TEAM VIEW: Only for managers/executives
                    logger.info(f"📍 FILTERING: Showing team/project tasks for project_id: {request.project_id}")
                    if request.project_id:
                        t_query = t_query.eq("project_id", request.project_id)

                # Skip query execution if RBAC already set data_context (permission denial)
                if data_context:
                    pass  # Already handled by RBAC block above
                else:
                    # Filter completed unless asked
                    if "completed" not in query.lower() and "history" not in query.lower():
                        # t_query = t_query.neq("status", "Completed") 
                        # Do python filtering instead for safety
                        pass
                        
                    res = await t_query.limit(100).execute()
                    tasks = res.data if res.data is not None else []
                    data_integrity["count"] = len(tasks)
                    if res.error: data_integrity["error"] = res.error
                
                    # Python-side filtering for robustness
                    filtered_tasks = []
                    target_name_lower = None
                    
                    for t in tasks:
                        s = str(t.get('status', '')).lower()
                        
                        # 1. Filter Completed
                        # SHOW ALL if query contains: "completed", "history", "total", "all", "count"
                        show_all = any(w in query.lower() for w in ["completed", "history", "total", "all", "count"])
                        
                        if not show_all:
                            if s == 'completed':
                                continue
                                
                        filtered_tasks.append(t)
                    
                    data_integrity["count"] = len(filtered_tasks)
                    if len(filtered_tasks) < len(tasks):
                        data_integrity["completeness"] = "partial_filtered"
                        data_integrity["filter_note"] = "Completed tasks are hidden. Ask 'show all tasks' to see them."

                    if not data_context:  # Only process if not already set by RBAC
                        if filtered_tasks:
                            # RULE 5 & 9: Provide insights instead of raw lists
                            # Analyze task data for meaningful summary
                            pending_count = sum(1 for t in filtered_tasks if t.get('status', '').lower() == 'pending')
                            in_progress_count = sum(1 for t in filtered_tasks if t.get('status', '').lower() == 'in progress')
                            overdue_count = 0
                            
                            # Check for overdue tasks
                            from datetime import datetime
                            today = datetime.now().date()
                            for t in filtered_tasks:
                                due_date_str = t.get('due_date')
                                if due_date_str and t.get('status', '').lower() not in ['completed', 'done']:
                                    try:
                                        due_date = datetime.fromisoformat(str(due_date_str).split('T')[0]).date()
                                        if due_date < today:
                                            overdue_count += 1
                                    except:
                                        pass
                            
                            # RULE 12: Improved data quality messaging
                            missing_data_note = ""
                            if any(not t.get('assigned_to_name') and not t.get('assigned_to') for t in filtered_tasks):
                                missing_data_note = "\n\n⚠️ Note: Some tasks are missing assignee information in the database."
                            
                            # GAP FIX: Summarize if list is too long (> 8 items)
                            if len(filtered_tasks) > 8:
                                task_counts = {"total": len(filtered_tasks), "high": 0, "medium": 0, "low": 0}
                                for t in filtered_tasks:
                                    p = t.get('priority', 'medium').lower()
                                    if p in task_counts: task_counts[p] += 1
                                
                                data_context = f"You have {len(filtered_tasks)} tasks ({pending_count} pending, {in_progress_count} in progress"
                                if overdue_count > 0:
                                    data_context += f", {overdue_count} overdue"
                                data_context += f"). Priority breakdown: {task_counts['high']} high, {task_counts['medium']} medium, {task_counts['low']} low. Please refine your query (e.g., 'show high priority tasks' or 'show overdue tasks') to see details.{missing_data_note}"
                            else:
                                # Provide insight-driven summary with selective details
                                task_list = []
                                for t in filtered_tasks:
                                     # Safe extraction of nested project name
                                     proj_data = t.get('projects')
                                     proj_name = proj_data.get('name') if proj_data else "General"
                                     task_list.append(f"- {t.get('title')} (Project: {proj_name}, Status: {t.get('status')}, Due: {t.get('due_date')}, Assigned: {t.get('assigned_to_name') or 'Unassigned'})") 
                                
                                summary = f"You have {len(filtered_tasks)} task{'s' if len(filtered_tasks) > 1 else ''}."
                                if overdue_count > 0:
                                    summary += f" ⚠️ {overdue_count} {'is' if overdue_count == 1 else 'are'} overdue."
                                if pending_count > 0:
                                    summary += f" {pending_count} pending."
                                
                                data_context = f"{summary}\n\n" + "\n".join(task_list) + missing_data_note
                        else:
                            data_context = "No tasks found matching the criteria."
            except Exception as e:
                data_context = f"Error fetching tasks: {e}"

        # 2. TEAMS / MEMBERS (Enhanced)
        elif action == "get_team_members":
            try:
                members = []
                source_desc = ""
                
                if request.project_id:
                    # Join project_members with profiles to get names
                    logger.info(f"📍 Fetching team members for project: {request.project_id}")
                    tm_query = supabase.table("project_members").select("user_id, profiles(full_name, role, email)").eq("project_id", request.project_id)
                    members = (await tm_query.execute()).data
                    source_desc = "project"
                elif request.org_id:
                    # Fallback: Show all org members
                    logger.info(f"📍 No project context, fetching org members for: {request.org_id}")
                    org_query = supabase.table("profiles").select("id, full_name, role, email").eq("org_id", request.org_id)
                    org_profiles = (await org_query.execute()).data
                    # Transform to match expected structure
                    members = [{"profiles": p} for p in org_profiles] if org_profiles else []
                    source_desc = "organization"
                
                if members:
                    m_list = []
                    for m in members:
                        profile = m.get("profiles")
                        if profile:
                            name = profile.get("full_name") or "Unknown"
                            role = profile.get("role") or "Member"
                            m_list.append(f"- {name} ({role})")
                    
                    data_context = f"Here are the team members ({source_desc}):\n" + "\n".join(m_list)
                else:
                    if request.project_id:
                        data_context = f"No team members found for this project. The project might not have any assigned members yet."
                    elif request.org_id:
                        data_context = f"No members found in this organization."
                    else:
                        data_context = "I couldn't identify your project or organization context to fetch team members. Please ensure you're logged in and have a project assigned."
            except Exception as e:
                logger.error(f"Error fetching team members: {e}")
                data_context = f"Error fetching team members: {e}"

        # 3. ATTENDANCE
        elif action == "get_attendance":
            try:
                from datetime import datetime
                today = datetime.now().strftime("%Y-%m-%d")
                a_query = supabase.table("attendance").select("*")
                
                # Check if user is asking specifically about today
                is_today_query = any(w in query.lower() for w in ["today", "this day", "current"])
                
                # Role-based restriction: Managers, Team Leads, and Executives can see team data
                privileged_roles = ["executive", "manager", "team_lead", "admin"]
                is_privileged = request.user_role.lower() in privileged_roles
                
                is_team_query = "team" in query.lower() or "everyone" in query.lower()
                
                if is_team_query and is_privileged:
                    logger.info(f"📍 FILTERING: Showing team attendance for org_id: {request.org_id}")
                    a_query = a_query.eq("org_id", request.org_id)
                else:
                    a_query = a_query.eq("employee_id", user_id)
                
                # If asking about today, filter to today
                if is_today_query:
                    a_query = a_query.eq("date", today)
                
                recs = (await a_query.order("date", desc=True).limit(100).execute()).data
                data_integrity["count"] = len(recs)
                
                if recs:
                    # Check for gaps in dates (simplified check)
                    if len(recs) < 5 and not is_today_query:
                         data_integrity["completeness"] = "low_data_warning"

                    # If asking about today specifically, show detailed time
                    if is_today_query and recs:
                        today_rec = recs[0]
                        clock_in_time = today_rec.get('clock_in')
                        clock_out_time = today_rec.get('clock_out')
                        if clock_in_time:
                            data_context = f"Here is the attendance for today ({today_rec.get('date')}):\n- Clock In: {clock_in_time}\n- Clock Out: {clock_out_time or 'Still clocked in'}"
                        else:
                            data_context = f"You have not clocked in today ({today})."
                    else:
                        present_count = len([r for r in recs if r.get('clock_in')])
                        
                        # GAP FIX: Summarize if list is too long (> 7 days)
                        if len(recs) > 7:
                            data_context = f"Attendance Summary:\n- Total Days Present (Recent): {present_count}\n- Latest Activity: {recs[0].get('date')} (In: {recs[0].get('clock_in')})\n\nPlease specify a date range for detailed logs."
                        else:
                            att_list = "\n".join([f"- {r.get('date')}: In {r.get('clock_in')}, Out {r.get('clock_out') or 'Still In'}" for r in recs[:10]])
                            data_context = f"Attendance Summary:\n- Total Days Present: {present_count}\n\nRecent History:\n{att_list}"
                else:
                    data_context = "No attendance records found."
            except Exception as e:
                data_context = f"Error fetching attendance: {e}"

        # 4. HIRING / JOBS (Real Implementation)
        elif action in ["get_hiring_overview", "get_jobs", "get_candidates"]:
            try:
                if action == "get_jobs":
                    j_res = await supabase.table("jobs").select("title, department, status, location").eq("org_id", request.org_id).execute()
                    if j_res.data:
                        j_list = "\n".join([f"- {j['title']} ({j['department']}) - Status: {j['status']}" for j in j_res.data])
                        data_context = f"Here are the current job openings:\n{j_list}"
                    else:
                        data_context = "No open job positions found in the database."
                
                elif action == "get_candidates":
                    c_res = await supabase.table("candidates").select("full_name, job_title, status").eq("org_id", request.org_id).execute()
                    if c_res.data:
                        c_list = "\n".join([f"- {c['full_name']} for {c['job_title']} - Status: {c['status']}" for c in c_res.data])
                        data_context = f"Here are the active candidates:\n{c_list}"
                    else:
                        data_context = "No candidate records found."
                
                else: # get_hiring_overview
                    j_count = (await supabase.table("jobs").select("id", count="exact").eq("org_id", request.org_id).execute()).count or 0
                    c_count = (await supabase.table("candidates").select("id", count="exact").eq("org_id", request.org_id).execute()).count or 0
                    data_context = f"Hiring Overview:\n- Open Positions: {j_count}\n- Active Candidates: {c_count}\n\nYou can ask for more details about 'jobs' or 'candidates' specifically."
            except Exception as e:
                logger.error(f"Hiring Data Error: {e}")
                data_context = "I couldn't fetch hiring data at this moment. The 'jobs' or 'candidates' tables might not be fully configured."

        # 5. USER PROFILE (Compliance with "What is my job title?")
        elif action == "get_my_profile":
            try:
                p_res = await supabase.table("profiles").select("*").eq("id", user_id).execute()
                if p_res.data:
                    p = p_res.data[0]
                    data_context = f"USER_PROFILE_DATA:\n- Name: {p.get('full_name')}\n- Job Title: {p.get('role')}\n- Email: {p.get('email')}\n- Organization: {p.get('org_id')}"
                else:
                    data_context = "I couldn't find your profile in the database."
            except Exception as e:
                 data_context = f"Error fetching profile: {e}."
 
        # 3. LEAVES & BALANCE (Enhanced)
        elif action in ["get_pending_leaves", "get_leave_balance"]:
            try:
                # Always fetch profile balance first for context
                p_resp = await supabase.table("profiles").select("total_leaves_balance, monthly_leave_quota, leaves_taken_this_month, leaves_remaining_this_month").eq("id", user_id).execute()
                profile = p_resp.data[0] if p_resp.data else None
                logger.info(f"📊 Profile fetched for {user_id}: {profile}")
                
                # Fetch leave requests
                l_query = supabase.table("leaves").select("from_date, to_date, reason, status, employee_id")
                
                if "team" not in query.lower() and "everyone" not in query.lower():
                    l_query = l_query.eq("employee_id", user_id)
                
                leaves = (await l_query.order("from_date", desc=True).limit(10).execute()).data
                data_integrity["count"] = len(leaves) if leaves else 0
                if profile and (profile.get('leaves_remaining') is None):
                    data_integrity["completeness"] = "missing_balance_field"
                
                # Format Balance (Very Explicit for LLM)
                if profile:
                    rem = profile.get('total_leaves_balance', 0)
                    rem_month = profile.get('leaves_remaining_this_month', 0)
                    quota = profile.get('monthly_leave_quota', 0)
                    taken = profile.get('leaves_taken_this_month', 0)
                    balance_str = f"CURRENT_LEAVE_BALANCE_DATA:\n- Total Balance Remaining: {rem} days\n- Remaining This Month: {rem_month} days\n- Monthly Allowance: {quota} days\n- Days Used This Month: {taken} days\n"
                else:
                    balance_str = "CURRENT_LEAVE_BALANCE_DATA: Profile balance not found."

                if leaves:
                    l_list = "\n".join([f"- {l.get('reason')} ({l.get('from_date')} to {l.get('to_date')}) - Status: {l.get('status')}" for l in leaves])
                    data_context = f"{balance_str}\nRECENT_LEAVE_HISTORY:\n{l_list}"
                else:
                    data_context = f"{balance_str}\nRECENT_LEAVE_HISTORY: No recent leave requests found."
            except Exception as e:
                data_context = f"Error fetching leaves: {e}"
        
        # 5. NOTIFICATIONS (Enhanced)
        elif action == "get_notifications":
            try:
                # Use correct column 'receiver_id' as verified from schema
                n_res = await supabase.table("notifications").select("*").eq("receiver_id", user_id).order("created_at", desc=True).limit(10).execute()
                
                recs = n_res.data
                if recs:
                    n_list = []
                    for r in recs:
                        sender = r.get('sender_name') or "System"
                        msg = r.get('message') or "No content"
                        status = "Read" if r.get('is_read') else "UNREAD"
                        time_str = (r.get('created_at') or '')[:16].replace('T', ' ')
                        n_list.append(f"- [{status}] {sender}: {msg} ({time_str})")
                    
                    data_context = f"Here are your most recent notifications from the database:\n" + "\n".join(n_list)
                else:
                    data_context = "No notifications found for your user ID in the database."
            except Exception as e:
                logger.error(f"Error fetching notifications: {e}")
                data_context = f"Error querying notifications: {str(e)}"

        # 5.1 PAYSLIPS (NEW: Logic for 'Module: My Tasks' hallucination fix)
        elif action == "get_payslips":
            try:
                logger.info(f"💰 Fetching payslips for user_id: {user_id}")
                # Fetch recent payroll records
                p_res = await supabase.table("payroll").select("*").eq("employee_id", user_id).order("month", desc=True).limit(3).execute()
                recs = p_res.data or []
                
                if recs:
                    p_list = []
                    for r in recs:
                        month = r.get('month', 'Unknown')
                        year = r.get('year', '')
                        net = r.get('net_pay', 0)
                        gross = r.get('gross_pay', 0)
                        deductions = r.get('deductions', 0)
                        p_list.append(f"- **{month} {year}**: Net Pay: ₹{net:,} (Gross: ₹{gross:,}, Deductions: ₹{deductions:,})")
                    
                    data_context = "PAYSLIP_DATA:\n" + "\n".join(p_list) + "\n\nYou can access full PDF payslips in the 'Pay and Benefits' section of the portal."
                else:
                    data_context = "No payslip records found in the database. If you have recently joined, your first payslip may not be generated yet."
            except Exception as e:
                logger.error(f"Error fetching payslips: {e}")
                data_context = f"I encountered an error while retrieving your payslip data: {str(e)}"

        # 6. ORG HIERARCHY
        elif action == "get_org_hierarchy":
            try:
                h_res = await supabase.table("profiles").select("id, full_name, role, job_title").order("full_name").execute()
                all_profiles = h_res.data or []
                
                user_level = get_role_level(user_role)
                if user_level >= 3:
                    profiles = all_profiles
                else:
                    my_proj_res = await supabase.table("project_members").select("project_id").eq("user_id", user_id).execute()
                    my_project_ids = {m["project_id"] for m in (my_proj_res.data or []) if m.get("project_id")}
                    if not my_project_ids:
                        profiles = [p for p in all_profiles if str(p.get("id")) == str(user_id)]
                    else:
                        m_res = await supabase.table("project_members").select("user_id, project_id").execute()
                        team_user_ids = {m["user_id"] for m in (m_res.data or []) if m.get("project_id") in my_project_ids}
                        profiles = [p for p in all_profiles if str(p.get("id")) in team_user_ids]
                        
                if profiles:
                    # Grouping by role
                    hierarchy = {}
                    for p in profiles:
                        role = p.get('role', 'Other').title().replace('_', ' ')
                        if role not in hierarchy:
                            hierarchy[role] = []
                        hierarchy[role].append(f"{p.get('full_name')} ({p.get('job_title', 'N/A')})")
                    
                    h_list = []
                    # Define order
                    order = ["Executive", "Manager", "Team Lead", "Employee", "Other"]
                    for role_name in order:
                        if role_name in hierarchy:
                            h_list.append(f"**{role_name}s:**")
                            for m in hierarchy[role_name]:
                                h_list.append(f"  - {m}")
                            del hierarchy[role_name]
                    
                    # Any remaining roles
                    for role_name, members in hierarchy.items():
                        h_list.append(f"**{role_name}:**")
                        for m in members:
                            h_list.append(f"  - {m}")
                    
                    data_context = "ORGANIZATION_HIERARCHY_DATA:\n" + "\n".join(h_list)
                else:
                    data_context = "No organization structure found in the database."
            except Exception as e:
                logger.error(f"Error fetching hierarchy: {e}")
                data_context = f"Error querying organization structure: {str(e)}"

        # 7. PROJECT HIERARCHY
        elif action == "get_project_hierarchy":
            try:
                # Fetch all projects, members and profiles
                p_res = await supabase.table("projects").select("*").execute()
                m_res = await supabase.table("project_members").select("*").execute()
                pr_res = await supabase.table("profiles").select("id, full_name").execute()
                
                all_projects = p_res.data or []
                members = m_res.data or []
                profiles = {p['id']: p['full_name'] for p in (pr_res.data or [])}
                
                user_level = get_role_level(user_role)
                if user_level >= 3:
                    projects = all_projects
                else:
                    my_project_ids = {m["project_id"] for m in members if str(m.get("user_id")) == str(user_id)}
                    projects = [p for p in all_projects if p.get("id") in my_project_ids]
                
                if projects:
                    p_list = []
                    for proj in projects:
                        p_name = proj.get('name', 'Unnamed Project')
                        p_list.append(f"### Project: {p_name}")
                        
                        # Get members for this project
                        p_members = [m for m in members if m['project_id'] == proj['id']]
                        
                        # Group members by role
                        role_groups = {}
                        for m in p_members:
                            r = m.get('role', 'Member').title().replace('_', ' ')
                            u_name = profiles.get(m['user_id'], "Unknown User")
                            if r not in role_groups:
                                role_groups[r] = []
                            role_groups[r].append(u_name)
                        
                        if not role_groups:
                            p_list.append("  - (No members assigned)")
                        else:
                            # Preferred order for display
                            for r_name in ["Manager", "Project Manager", "Team Lead", "Employee"]:
                                if r_name in role_groups:
                                    p_list.append(f"  **{r_name}s:**")
                                    for user in role_groups[r_name]:
                                        p_list.append(f"    - {user}")
                                    del role_groups[r_name]
                            
                            for r_name, users in role_groups.items():
                                p_list.append(f"  **{r_name}s:**")
                                for user in users:
                                    p_list.append(f"    - {user}")
                        p_list.append("") # Spacer
                    
                    data_context = "PROJECT_HIERARCHY_DATA:\n" + "\n".join(p_list)
                else:
                    data_context = "No projects found in the database."
            except Exception as e:
                logger.error(f"Error fetching project hierarchy: {e}")
                data_context = f"Error querying project structure: {str(e)}"

        # 8. EVENTS
        elif action == "get_events":
            try:
                # ... (existing event fetching logic)
                e_query = supabase.table("events").select("*")
                if request.org_id:
                    e_query = e_query.eq("org_id", request.org_id)
                if request.project_id:
                    e_query = e_query.eq("project_id", request.project_id)
                recs = (await e_query.order("start_time", desc=False).limit(10).execute()).data
                if recs:
                    event_list = "\n".join([f"- {r.get('title')} ({r.get('start_time')} to {r.get('end_time')})" for r in recs])
                    data_context = f"Here are the upcoming events:\n{event_list}"
                else:
                    data_context = "No events found matching the criteria."
            except Exception as e:
                data_context = f"Error querying events: {str(e)}"

        elif action == "get_policies":
            try:
                p_query = supabase.table("policies").select("*")
                if request.org_id:
                    p_query = p_query.eq("org_id", request.org_id)
                recs = (await p_query.eq("status", "Active").order("created_at", desc=True).limit(20).execute()).data
                if recs:
                    p_list = "\n".join([f"- {r.get('title')} ({r.get('category')})" for r in recs])
                    data_context = f"The following active policies are available:\n{p_list}\n\nYou can ask me specific questions about their content!"
                else:
                    data_context = "No active company policies found in the database."
            except Exception as e:
                logger.error(f"Error in get_policies: {e}")
                data_context = f"Error fetching policies: {e}"

        elif action == "get_project_documents":
            try:
                found_docs = []
                logger.info(f"📁 get_project_documents: Searching for project_id={request.project_id}, org_id={request.org_id or org_id}")
                
                # Try Project level
                if request.project_id:
                    d_res = await supabase.table("documents").select("title, id").eq("project_id", request.project_id).execute()
                    if d_res.data: 
                        found_docs = d_res.data
                        logger.info(f"✅ Found {len(found_docs)} docs at project level")
                
                # Try Org level if still empty
                if not found_docs and (request.org_id or org_id):
                    target_org = request.org_id or org_id
                    d_res = await supabase.table("documents").select("title, id").eq("org_id", target_org).execute()
                    if d_res.data: 
                        found_docs = d_res.data
                        logger.info(f"✅ Found {len(found_docs)} docs at org level ({target_org})")
                
                # Try Global Fallback if still empty
                if not found_docs:
                    logger.info("⚠️ No docs found at project/org level, trying global search...")
                    d_res = await supabase.table("documents").select("title, id").execute()
                    if d_res.data: 
                        found_docs = d_res.data
                        logger.info(f"✅ Found {len(found_docs)} docs globally")
                
                if found_docs:
                    d_list = "\n".join([f"- {d.get('title')} (@{d.get('title').replace(' ', '_')})" for d in found_docs])
                    data_context = f"The following documents are available in the current context:\n{d_list}\n\nYou can ask me specific questions about them by using the @tag!"
                else:
                    logger.warning("❌ No documents found in database at all!")
                    data_context = "I couldn't find any documents attached to this project or organization in the database."
            except Exception as e:
                logger.error(f"Error in get_project_documents: {e}")
                data_context = f"Error fetching documents: {e}"

        # 10. ANALYTICS (Cross-Module Insights)
        elif action == "get_analytics":
            try:
                # Fetch Tasks Progress
                t_res = await supabase.table("tasks").select("status").eq("assigned_to", user_id).execute()
                tasks = t_res.data or []
                total_tasks = len(tasks)
                completed_tasks = len([t for t in tasks if t.get("status") == "completed"])
                pending_tasks = total_tasks - completed_tasks
                
                # Fetch Attendance Consistency (Last 30 days)
                a_res = await supabase.table("attendance").select("date").eq("employee_id", user_id).limit(30).execute()
                attendance = a_res.data or []
                working_days = len(attendance)
                
                # Fetch Leave Balance
                p_res = await supabase.table("profiles").select("leaves_remaining").eq("id", user_id).execute()
                leaves_rem = p_res.data[0].get("leaves_remaining", 0) if p_res.data else 0
                
                data_context = f"""
                ANALYTICAL_SUMMARY for {app_name.title()}:
                - Task Completion: {completed_tasks}/{total_tasks} tasks done ({pending_tasks} pending).
                - Attendance: {working_days} active days recorded in the last 30 days.
                - Leave Security: {leaves_rem} days currently remaining in balance.
                
                This data allows you to provide insights on productivity trends and work-life balance.
                """
                logger.info("📊 Rule 4 Check: Analytics context generated.")
            except Exception as e:
                logger.error(f"Analytics Error: {e}")
                data_context = f"I encountered an error while synthesizing your analytics: {str(e)}"

        elif action == "present_rag":
            data_context = f"RAG_DOCUMENT_NAME: {request.rag_source}\nSOURCE: {request.rag_source}\nCONTENT: {request.rag_content}"

        elif action == "chat":
            # FIX 6: Helpful fallback menu with real UI module names (per role)
            role_lower = user_role.lower().replace(" ", "_")
            if role_lower in ["employee", "consultant"]:
                help_menu = (
                    "- 📋 **My Tasks** — 'Show my tasks' or 'Show overdue tasks'\n"
                    "- 🕐 **Attendance** — 'Clock me in' or 'Show my attendance'\n"
                    "- 🏖️ **Leave Requests** — 'Apply for leave' or 'Check my leave balance'\n"
                    "- 💰 **Payslip** — 'Show my payslip'\n"
                    "- 📢 **Announcements** — 'Show announcements'\n"
                    "- 📊 **My Analytics** — 'Show my analytics'\n"
                    "- 📝 **Project Documents** — 'Show project documents'\n"
                    "- 📜 **Company Policies** — 'Show policies'"
                )
            elif role_lower in ["team_lead", "teamlead"]:
                help_menu = (
                    "- 📋 **Tasks** — 'Show team tasks' or 'Assign a task'\n"
                    "- 🕐 **Team Status** — 'Show team attendance'\n"
                    "- 🏖️ **Leave Requests** — 'Show pending leaves' or 'Approve a leave'\n"
                    "- 📊 **Analytics** — 'Show team analytics'\n"
                    "- 👥 **Team Members** — 'Show team members'\n"
                    "- 💰 **Payslips** — 'Show my payslip'"
                )
            elif role_lower == "manager":
                help_menu = (
                    "- 📋 **All Tasks** — 'Show all tasks' or 'Assign task to [Name]'\n"
                    "- 👥 **Employees** — 'Show all employees' or 'Show employee status'\n"
                    "- 🏖️ **Leave Requests** — 'Show pending leaves' or 'Approve leave for [Name]'\n"
                    "- 💼 **Hiring Portal** — 'Show job openings' or 'Show candidates'\n"
                    "- 📊 **Analytics** — 'Show analytics'\n"
                    "- 📞 **Project Members** — 'Show project team members'"
                )
            else:  # executive
                help_menu = (
                    "- 📊 **Analytics** — 'Show org analytics' or 'Show project analytics'\n"
                    "- 📋 **All Tasks** — 'Show all tasks'\n"
                    "- 🏖️ **Leave Requests** — 'Show all pending leaves'\n"
                    "- 💼 **Hiring Portal** — 'Show hiring overview' or 'Show candidates'\n"
                    "- 👥 **Employees** — 'Show all employees'\n"
                    "- 🏢 **Project Management** — 'Show project status'\n"
                    "- 💰 **Payslips** — 'Show payroll overview'"
                )
            data_context = params.get("llm_response") or f"I’m not sure I understood that correctly. Here’s what I can help you with:\n\n{help_menu}\n\nJust type any of the above or ask a question!"

        elif action == "greeting":
            # FIX 5: Role-specific greeting with real UI module names
            role_lower = user_role.lower().replace(" ", "_")
            user_name = (request.context.get("name") or "there") if request.context else "there"
            if role_lower in ["employee", "consultant"]:
                greeting_options = "📋 My Tasks | 🕐 Clock In/Out | 🏖️ Leave Requests | 💰 My Payslip | 📊 My Analytics | 📢 Announcements"
            elif role_lower in ["team_lead", "teamlead"]:
                greeting_options = "📋 Tasks | 🕐 Team Status | 🏖️ Leave Requests | 📊 Analytics | 👥 Team Members"
            elif role_lower == "manager":
                greeting_options = "📋 All Tasks | 🏖️ Leave Requests | 💼 Hiring Portal | 📊 Analytics | 👥 Employees"
            else:  # executive
                greeting_options = "📊 Analytics | 📋 All Tasks | 🏖️ Leave Requests | 💼 Hiring Portal | 🏢 Project Management"
            data_context = f"Greet the user warmly as '{user_name}' and tell them you are ready to help. Mention these quick actions they can ask about: {greeting_options}. Keep it brief and professional."

        else:
            data_context = f"ACTION_DETECTED: {action}. Please respond based on the data context or offer general assistance."
            
        # --- RULE 14: NO HALLUCINATION CHECK ---
        # If data_context is empty or indicates no data, return immediately
        no_data_indicators = [
            "No records found", "No data found", "couldn't find any", 
            "No tasks found", "No attendance records", "No events found",
            "No documents", "No members found", "No open job positions",
            "No candidate records", "couldn't find your profile"
        ]
        
        if any(indicator in data_context for indicator in no_data_indicators):
            logger.info("🛡️ RULE 14: No data found, returning explicit message")
            # Determine likely module for prefixing
            mod_prefix = "Chat"
            if action in ["get_tasks", "assign_task", "create_task"]: mod_prefix = "My Tasks"
            elif action in ["get_attendance", "clock_in", "clock_out"]: mod_prefix = "Attendance"
            elif action in ["get_pending_leaves", "get_leave_balance", "apply_leave"]: mod_prefix = "Leaves"
            elif action in ["get_team_members", "get_org_hierarchy", "get_project_hierarchy"]: mod_prefix = "Organization"
            elif action == "get_analytics": mod_prefix = "Analytics"
            elif action == "get_project_documents": mod_prefix = "Project Documents"
            elif action == "get_policies": mod_prefix = "Policies"
            elif action == "get_payslips": mod_prefix = "Payslips"
            elif "policy" in data_context.lower() or "policy" in query.lower(): mod_prefix = "Policies"
            
            return SLMQueryResponse(
                response=f"**Module:** {mod_prefix}\n**User Role:** {request.user_role}\n\nI checked the database, but {data_context.lower()}",
                action=action,
                data={"no_data": True}
            )
            
        # --- RULE 12 STRICT ENFORCEMENT ---
        if data_integrity.get("completeness") == "partial":
            logger.info("🛡️ RULE 12 INTERCEPT: Prefixing data payload with completeness warning")
            missing = data_integrity.get("missing_fields", "some relevant fields")
            data_context = f"WARNING [RULE 12]: The following data is incomplete because {missing} are missing.\n\n{data_context}"
            
        # --- LLM RESPONSE SYNTHESIS ---
        # No more "Fast Path" returns. Every response is synthesized by the LLM to ensure
        # insight-driven summaries and compliance with all rules (Rule 9, 11, etc).

        response_prompt = f"""### SYSTEM ROLE
You are the {app_name.title()} AI Assistant.

This prompt applies when the user’s question relates to:
- My Tasks
- Team Tasks
- Attendance
- Leaves
- Payslips / Payroll / Salary
- Analytics
- Organization Hierarchy
- Policies
- Project Documents / Knowledge Base

Your responsibility is to provide insight-driven, role-safe, and data-backed responses while strictly following product rules.

Core Rules:

1. **MANDATORY MODULE IDENTIFICATION:** You MUST start your response with the exact module name and your role.
   - For Tasks -> "**Module:** My Tasks"
   - For Attendance -> "**Module:** Attendance"
   - For Leaves/Balance -> "**Module:** Leaves"
   - For Analytics -> "**Module:** Analytics"
   - For Members/Structure -> "**Module:** Organization"
   - For Policies -> "**Module:** Policies"
   - For Documents -> "**Module:** Project Documents"
   - For Payslips -> "**Module:** Payslips"
   
   Format: "**Module:** [Name] \n**User Role:** [Role]\n\n[Your response content...]"

2. Enforce Role-Based Access Control (RBAC) strictly:
   - Employees can access only their own tasks and analytics.
   - Team Leads can access their own tasks, team tasks, and team-level analytics.
   - Managers can access employee tasks and cross-team analytics.
   - Executives can access organization-level analytics only.

3. Never expose data outside the user’s authorized scope, including during comparisons, summaries, or explanations.

4. If the requested information is already clearly visible in the current UI/module, redirect the user to that module instead of repeating raw data.

5. If the information is not directly visible or requires reasoning, provide a clear, concise, and meaningful summary or explanation based on the data.

6. You must support simple, complex, comparative, and analytical questions related to all supported modules (Tasks, Attendance, Leaves, Payslips, Documents, and Analytics).

7. You may analyze and compare data across multiple tables, columns, users, projects, and time periods when required, while remaining within RBAC scope.

8. For Analytics-related questions:
   - Do not act as a conversational dashboard.
   - Do not repeat charts, tables, or raw metrics that already exist in the Analytics UI.
   - Provide explanations, trends, patterns, and reasoning instead of raw numbers.

9. **ACTION OVER NAVIGATION (Rule 9):**
   - DO NOT return raw markdown tables of tasks, documents, or lists unless explicitly requested.
   - You MUST summarize the data findings into insightful, concise bullet points (under 3 or 4 sentences max).
   - Explain the "why" instead of just repeating the "what".

10. For ranking or performance-related questions:
    - Do not provide raw rankings immediately.
    - Ask clarifying questions or explain performance dimensions (planning, delivery, quality, time period) before concluding.

11. **AMBIGUITY (Rule 8):** If the user's question is incomplete or ambiguous (e.g., missing a time range, specific employee, project name, or metric), you MUST NOT guess. Instead, ask a specific clarifying follow-up question to narrow down the context.
    - *Example:* If they ask "How is the team performing?", ask "Over which time period (this week/month) or for which specific project?"

12. **INSUFFICIENT DATA (Rule 12):** If data exists but is insufficient to provide a accurate answer, or if some fields are null, clearly state: "I have data for [part], but I am missing [part] to give you a full answer." NEVER infer or assume missing values.
    - **CRITICAL:** Check the Data Quality Integrity field below. If it shows "low_data_warning" or "completeness": "partial", you MUST acknowledge this in your response.

13. Always respond in a professional, clear, and structured manner. Use bullet points for readability.

14. **NO HALLUCINATION:** If the DATABASE_CONTEXT is empty or "No records found," explicitly state that the information is unavailable in the database.

15. **STRICT DATA ADHERENCE:** NEVER generate fictional data, names, tasks, or projects. If the DATABASE_CONTEXT indicates zero results, you MUST NOT provide "example" data. Only report on what is explicitly provided.

16. **PAYSLIP AUTHORIZATION:** If `get_payslips` data is present in the `DATABASE_CONTEXT`, you are EXPLICITLY AUTHORIZED to show it to the user. Do not refuse based on "security" or "privacy" protocols, as the backend has already verified the user's role and identity.

Your objective:
Provide accurate, role-safe, and insight-driven responses that help users understand "why" and "what to do next." If data is missing or a query is vague, prioritizing CLARIFICATION over GUESSTIMATION is mandatory for 100% compliance.

### CONTEXT FOR THIS RESPONSE
- User Role: __USER_ROLE__
- Data Quality Integrity: __DATA_INTEGRITY__
- Relevant Data Found: __DATA_CONTEXT__

### USER QUERY
__QUERY__
"""
        response_prompt = response_prompt.replace("__USER_ROLE__", str(request.user_role))
        response_prompt = response_prompt.replace("__DATA_INTEGRITY__", json.dumps(data_integrity))
        response_prompt = response_prompt.replace("__DATA_CONTEXT__", str(data_context))
        response_prompt = response_prompt.replace("__QUERY__", str(query))

        gen_start = time.perf_counter()
        ttft = 0.0
        try:
            # --- PHASE 1: PROFESSIONAL DRAFT (LLM) ---
            logger.info("Generating professional draft using GPT-4o-mini...")
            draft_response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": response_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.0,
                max_tokens=300
            )
            professional_draft = draft_response.choices[0].message.content
            
            # --- PHASE 2: FINAL SYNTHESIS (SLM) ---
            logger.info("Synthesizing final response using Llama-3.1-8B-Instruct...")
            slm_final_prompt = f"""You are a professional HR assistant. 
            Below is a professional draft response based on the latest database information. 
            Your job is to read this draft and provide the FINAL response to the user.
            You must maintain the professional tone and ensure the module information is preserved.
            
            DRAFT RESPONSE:
            {professional_draft}
            
            USER QUERY:
            {query}
            
            Provide the FINAL response below:"""
            
            final_response_completion = await together_client.chat.completions.create(
                model="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                messages=[
                    {"role": "system", "content": "You are a professional workplace assistant."},
                    {"role": "user", "content": slm_final_prompt}
                ],
                temperature=0.0,
                max_tokens=400
            )
            
            # Check if we got a coroutine back (SDK safety)
            if asyncio.iscoroutine(final_response_completion):
                final_response_completion = await final_response_completion
                
            final_response = final_response_completion.choices[0].message.content
            ttft = time.perf_counter() - gen_start # Rough estimate for the whole chain

            total_end = time.perf_counter()
            total_latency = total_end - total_start
            generation_latency = total_end - gen_start
            tokens_generated = len(final_response.split())

            model_label = "RAG" if is_rag_triggered else "SLM"
            log_latency(
                model_label, 
                ttft, 
                total_latency, 
                generation_latency, 
                tokens_generated,
                retrieval_latency=rag_metrics.get("retrieval_latency", 0.0),
                embedding_latency=rag_metrics.get("embedding_latency", 0.0)
            )
        except Exception as e:
            logger.error(f"❌ LLM Response Synthesis Error: {e}")
            total_latency = time.perf_counter() - total_start
            model_label = "RAG" if is_rag_triggered else "SLM"
            log_latency(model_label, 0, total_latency, 0, 0, status="error")
            # Fallback response if LLM fails
            if data_context and "No" not in data_context[:20]:
                final_response = f"Based on the data I found:\n\n{data_context[:500]}"
            else:
                final_response = "I encountered an issue processing your request. Please try again or rephrase your question."
        
        # [CRITICAL FIX] 
        # Only override to "chat" if no specific action was detected.
        if not action or action == "chat":
            action = "chat"
            
        # --- CACHE NEW RESPONSE ---
        if not request.forced_action and final_response:
             # Using background tasks to not block response delivery
             if hasattr(request, 'background_tasks') and request.background_tasks:
                 request.background_tasks.add_task(save_semantic_cache, query, final_response, org_id, user_id, user_role, project_id)
             else:
                 # Fallback for if BackgroundTasks isn't passed through (we should ensure it is)
                 asyncio.create_task(save_semantic_cache(query, final_response, org_id, user_id, user_role, project_id))

        # --- FIX 7: SMART SUGGESTIONS with real UI page names (per role) ---
        # Role-aware: Employee uses /employee-dashboard/..., Executive uses /executive-dashboard/...
        role_lower_s = user_role.lower().replace(" ", "_") if user_role else "employee"
        is_exec = role_lower_s == "executive"
        is_mgr  = role_lower_s == "manager"
        is_tl   = role_lower_s in ["team_lead", "teamlead"]
        is_emp  = not (is_exec or is_mgr or is_tl)

        ACTION_SUGGESTIONS = {
            "get_tasks": (
                ["Show overdue tasks", "Show high priority tasks", "Mark a task done", "📋 View Tasks page →"]
                if is_emp else
                ["Assign task to a team member", "Show overdue tasks", "Filter by status", "📋 View All Tasks →"]
            ),
            "assign_task":      ["Show team tasks", "View team members", "📋 View Tasks page →"],
            "get_attendance": (
                ["Clock me in", "Show this week\'s attendance", "🕐 View Attendance page →"]
                if is_emp else
                ["Show team attendance", "Show employee status", "🕐 View Team Status →"]
            ),
            "clock_in":         ["Show my attendance today", "Check my tasks", "🕐 View Attendance page →"],
            "clock_out":        ["Show my attendance today", "Apply for leave", "🕐 View Attendance page →"],
            "get_leave_balance":["Apply for leave", "Show my leave history", "🏖️ View Leave Requests →"],
            "apply_leave":      ["Check leave balance", "Show my leaves", "🏖️ View Leave Requests →"],
            "approve_leave":    ["Show all pending leaves", "View team members", "🏖️ View Leave Requests →"],
            "reject_leave":     ["Show all pending leaves", "View team members", "🏖️ View Leave Requests →"],
            "get_hiring_overview": ["Show job openings", "Show candidates", "💼 View Hiring Portal →"],
            "get_notifications":["Show my tasks", "Show announcements", "🔔 View Notifications →"],
            "get_analytics": (
                ["Show my tasks summary", "Check attendance record", "📊 View My Analytics →"]
                if is_emp else
                ["Show team performance", "View project analytics", "📊 View Analytics →"]
            ),
            "get_project_documents": ["Ask about a document", "Search for a policy", "📝 View Project Documents →"],
            "get_policies":          ["Ask about a specific policy", "Show announcements", "📜 View Policies →"],
            "get_announcements":     ["Show my tasks", "Show notifications", "📢 View Announcements →"],
            "get_team_members":      ["Show team tasks", "Show team attendance", "👥 View Team Members →"],
            "greeting":  (["Show my tasks", "Clock me in", "Check leave balance"] if is_emp else
                          ["Show team tasks", "Show pending leaves", "Show team attendance"] if is_tl else
                          ["Show all tasks", "Show pending leaves", "Check hiring status"] if is_mgr else
                          ["Show org analytics", "Show all tasks", "Check hiring overview"]),
            "chat":      (["Show my tasks", "Clock me in", "Check leave balance"] if is_emp else
                          ["Show team tasks", "Show team attendance", "Show pending leaves"] if is_tl else
                          ["Show all tasks", "Show pending leaves", "Show hiring overview"] if is_mgr else
                          ["Show org analytics", "Show project analytics", "Show all tasks"]),
        }
        suggestions = ACTION_SUGGESTIONS.get(action, ["Show my tasks", "Check my attendance", "Check leave balance"])

        # --- FIX 8: ROLE-AWARE DESCRIPTIVE NAVIGATION LINKS (real UI routes) ---
        def _nav(label: str, path: str) -> str:
            # Map roles to their specific dashboard base paths
            if is_exec: base = "/executive-dashboard"
            elif is_mgr: base = "/manager-dashboard"
            elif is_tl: base = "/teamlead-dashboard"
            else: base = "/employee-dashboard"
            return f"{label} [{base}{path}]"

        NAV_LINK_TEXT = {
            "get_tasks":          (
                _nav("📋 View all your tasks on My Tasks page →", "/my-tasks") if is_emp
                else _nav("📋 View All Tasks page →", "/tasks") if is_exec or is_mgr
                else _nav("📋 View Team Tasks page →", "/team-tasks")
            ),
            "assign_task":        _nav("📋 View Tasks page →", "/tasks" if is_exec else "/team-tasks"),
            "get_attendance":     (
                _nav("🕐 View your full Attendance on Team Status page →", "/team-status") if is_emp
                else _nav("🕐 View Employee Status page →", "/employee-status")
            ),
            "clock_in":           (
                _nav("🕐 View your Attendance on Team Status page →", "/team-status") if is_emp
                else _nav("🕐 View Employee Status page →", "/employee-status")
            ),
            "clock_out":          (
                _nav("🕐 View your Attendance on Team Status page →", "/team-status") if is_emp
                else _nav("🕐 View Employee Status page →", "/employee-status")
            ),
            "get_leave_balance":  _nav("🏖️ View your Leave Requests page →", "/leaves"),
            "apply_leave":        _nav("🏖️ Track your leave on Leave Requests page →", "/leaves"),
            "approve_leave":      (
                _nav("🏖️ View all Leave Requests →", "/leaves") if is_exec or is_mgr
                else _nav("🏖️ View Team Leave Requests →", "/approve-leaves")
            ),
            "reject_leave":       (
                _nav("🏖️ View all Leave Requests →", "/leaves") if is_exec or is_mgr
                else _nav("🏖️ View Team Leave Requests →", "/approve-leaves")
            ),
            "get_hiring_overview": _nav("💼 View the full Hiring Portal →", "/hiring"),
            "get_notifications":  _nav("🔔 View all Notifications →", "/notifications"),
            "get_analytics":      _nav("📊 View Analytics page →", "/analytics"),
            "get_project_documents": (
                _nav("📝 View Project Documents →", "/employees") if is_emp else
                _nav("📝 View Project Documents →", "/project") if is_tl else
                _nav("📝 View Project Documents →", "/documents") # mgr and exec
            ),
            "get_policies":          _nav("📜 View Company Policies →", "/policies"),
            "get_team_members":      (
                _nav("👥 View Team Members page →", "/team-members") if is_emp
                else _nav("👥 View Employees page →", "/employees")
            ),
        }
        nav_link = NAV_LINK_TEXT.get(action, "")

        # Append nav link to final_response if applicable
        if nav_link and final_response and "ERROR" not in final_response[:10]:
            final_response = f"{final_response}\n\n{nav_link}"

        return SLMQueryResponse(
            response=final_response,
            action=action,
            data=params, # Removed suggestions from here
            suggestions=suggestions, # Added at top level
            intent_model="Meta-Llama-3.1-8B-Instruct-Turbo (SLM)",
            synthesis_model="Meta-Llama-3.1-8B-Instruct-Turbo (SLM)"
        )
        
    except Exception as e:
        logger.error(f"SLM Chat Error: {e}")
        return SLMQueryResponse(
            response=f"I encountered an error processing your request. Please try again.",
            action="error",
            data={"error": str(e)},
            suggestions=["Try again", "Show my tasks"]
        )

@app.get("/slm/tasks")
@app.get("/api/tasks")
async def get_tasks(user_id: Optional[str] = None):

    try:
        query = supabase.table("tasks").select("*")
        if user_id:
            query = query.eq("assigned_to", user_id)
        result = await query.limit(50).execute()
        return {"tasks": result.data, "count": len(result.data)}
    except Exception as e:
        return {"tasks": [], "error": str(e)}

@app.get("/slm/attendance")
@app.get("/api/attendance")
async def get_attendance(user_id: Optional[str] = None, date: Optional[str] = None):

    try:
        query = supabase.table("attendance").select("*")
        if user_id:
            query = query.eq("employee_id", user_id)
        if date:
            query = query.eq("date", date)
        result = await query.limit(50).execute()
        return {"attendance": result.data, "count": len(result.data)}
    except Exception as e:
        return {"attendance": [], "error": str(e)}

# =============================================================================
# LLM ENDPOINTS (OpenAI with Guardrails)
# =============================================================================
# LLMQueryRequest and LLMQueryResponse have been moved to 'binding'


# =============================================================================
# USER CONTEXT HELPER
# =============================================================================
async def fetch_user_context(user_id: str) -> Dict[str, Any]:

    context = {
        "user_id": user_id,
        "name": "Unknown User",
        "role": "employee",
        "email": "",
        "project_id": None,
        "project_name": None,
        "org_id": None
    }
    
    try:
        # 1. Fetch Basic Profile
        # switched to 'profiles' as 'users' returned 404
        user_resp = await supabase.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        if user_resp.data:
            user = user_resp.data[0]
            context["name"] = user.get("full_name") or user.get("name", "User")
            context["role"] = user.get("role", "employee")
            context["email"] = user.get("email", "")
            
        # 2. Fetch Active Project
        # Assuming one active project per user for now
        proj_resp = await supabase.table("project_members").select("project_id, projects(name, org_id)").eq("user_id", user_id).limit(1).execute()
        if proj_resp.data:
            membership = proj_resp.data[0]
            context["project_id"] = membership.get("project_id")
            
            # Extract joined project details
            project_details = membership.get("projects")
            if project_details:
                context["project_name"] = project_details.get("name")
                context["org_id"] = project_details.get("org_id") # Often projects are linked to orgs

        # 3. If org_id still missing, check organization_members
        if not context["org_id"]:
             org_resp = await supabase.table("organization_members").select("organization_id").eq("user_id", user_id).limit(1).execute()
             if org_resp.data:
                 context["org_id"] = org_resp.data[0].get("organization_id")

        return context
        
    except Exception as e:
        logger.error(f"Error fetching user context for {user_id}: {e}")
        return context

# Load system prompt for LLM
LLM_SYSTEM_PROMPT = """You are a professional workplace assistant for TalentOps HR platform.
You help with HR-related queries, task management, attendance, leaves, and workplace policies.
Stay focused on workplace topics only. Politely decline non-work related queries.

CURRENT USER CONTEXT:
Name: {user_name}
Role: {user_role}
Project: {project_name}
"""

ORCHESTRATOR_SYSTEM_PROMPT = """You are an intelligent router for the TalentOps ecosystem.
Your job is to analyze the users query and route it to the correct backend system.

Output strictly a JSON object: {"system": "slm" | "rag" | "llm", "reason": "short explanation"}

GUIDELINES:
1. "slm": Use for ANY live action or database query:
   - USER DATA: "my tasks", "my attendance", "my balance", "my notifications", "recent alerts".
   - TEAM/MANAGER DATA: "team tasks", "approve leave", "assign task", "team attendance", "who is in my team".
   - PERSONAL ACTIONS: "Clock me in", "Clock me out", "Apply for leave".
   - ADMINISTRATIVE: "Post announcement", "Create project", "Add user to project".
   - NAVIGATION: "go to leaves page", "open my tasks", "redirect to dashboard", "show me the attendance module".
   - ORGANIZATION: "Org hierarchy", "Who is in the team", "Company structure".
   - PROJECTS: "Project hierarchy", "Project team", "Who is working on project X".
   - HIRING: "Job openings", "Candidates", "Recruitement status".
   - CRITICAL: Anything involving live database records, navigation/redirection, or performing an operation.

2. "rag": Use ONLY for static document knowledge, technical specs, or manuals:
   - "What is the policy for X?", "Information from document Y", "Handbook rules", "SOP guide".
   - "Architecture details", "Technical specs", "How does the system work?", "Module documentation".
   - If the query asks for information found in documents, ALWAYS use RAG.

3. "llm": Use ONLY for general greetings or non-work casual chat.
4. "Policies": If the user asks for a LIST of policies, use "slm". If they ask about the CONTENT of a specific policy, use "rag".
"""

# Keywords that suggest RAG (Document & Policy Queries)
RAG_KEYWORDS = [
    "policy guide", "handbook", "procedure manual", "holiday rules", "expense policy", 
    "hr guide", "what is the policy", "regulations", "company guidelines", "sop",
    "standard operating procedure", "compliance", "code of conduct", "employee manual",
    "benefits guide", "onboarding guide", "training material", "project documentation",
    "technical specs", "requirements document", "what does the document say",
    "read the policy", "check the handbook", "according to the manual",
    "architecture", "frontend", "backend", "system design", "technical details",
    "module overview", "technical documentation", "search documents", "read document",
    "document content", "tell me about this document", "inside the document",
    "what is in", "what does the doc say", "according to", "manual", "guide", "specs", "specification"
]

# Keywords that suggest SLM (Actions & Data Queries for TalentOps)
SLM_KEYWORDS = [
    # Task Management
    "assign task", "create task", "update task", "delete task", "my tasks", "task status",
    "pending tasks", "completed tasks", "overdue tasks", "task deadline", "task priority",
    
    # Attendance & Time Tracking
    "clock in", "clock out", "my attendance", "attendance history", "mark attendance",
    "check in", "check out", "time log", "working hours", "late today", "am i late",
    "active", "online", "present", "working today", "who is working", "who is active",
    
    # Leave Management
    "apply leave", "request leave", "my leaves", "leave balance", "leave allowance",
    "remaining leaves", "leave history", "cancel leave", "pending leave requests",
    "approve leave", "reject leave", "sick leave", "casual leave", "vacation",
    
    # Team & People
    "my team", "team members", "who is in my team", "team attendance", "team tasks",
    "assigned to me", "assigned to", "team lead", "manager", "colleagues",
    
    # Announcements & Communication
    "post announcement", "broadcast", "send message", "notify team", "announce",
    "create announcement", "company announcement", "notifications", "my alerts",
    "recent notifications", "what are my notifications", "show notifications",
    
    # Documents & Files
    "project documents", "show me project documents", "list files", "my documents", "what documents",
    "view documents", "available documents", "get documents", "show documents",
    "policies", "show policies", "list policies", "company policies", "hr policies",
    
    # Projects
    "create project", "update project", "project status", "my projects", "project members",
    "add member", "remove member", "project deadline",
    
    # Hiring & Recruitment
    "hiring overview", "job openings", "candidates", "applicants", "interview schedule",
    "shortlist candidate", "recruitment status",
    
    # Performance & Reports
    "my performance", "team performance", "attendance report", "task report",
    "productivity", "kpi", "metrics",
    
    # Organization
    "org hierarchy", "org chart", "hierarchy chart", "company structure", "reporting lines",
    "who is in the company", "list all employees", "team structure",
    
    # Navigation & UI (Requirement 4)
    "go to", "open page", "navigate to", "redirect to", "show module", "open module", 
    "show page", "take me to",
    
    # Project Specific Hierarchy
    "project hierarchy", "project team", "who is on the project", "project structure",
    "project leads", "project members"
]

@app.post("/llm/query")
@app.post("/api/llm/query")
async def llm_query(request: LLMQueryRequest):

    start_time = time.perf_counter()
    
    # Rate Limiting (Phase 2.3)
    if not await rate_limiter.consume("llm_global", tokens=1):
        raise HTTPException(status_code=429, detail="Global LLM Rate Limit Exceeded")
        
    ttft = 0.0
    try:
        messages = [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": request.query}
        ]
        
        # Capture streaming for TTFT and token count
        response_stream = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True
        )
        
        full_content = ""
        tokens_generated = 0
        async for chunk in response_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                if not full_content:
                    ttft = time.perf_counter() - start_time
                full_content += chunk.choices[0].delta.content
                # Simple token approximation (splitting by whitespace)
                # For high precision we could use tiktoken, but requirement says "minimal, clean"
            if chunk.choices and chunk.choices[0].finish_reason:
                pass

        total_latency = time.perf_counter() - start_time
        generation_latency = total_latency - ttft
        tokens_generated = len(full_content.split()) # Rough estimate per requirement
        
        log_latency("LLM", ttft, total_latency, generation_latency, tokens_generated)
        
        return LLMQueryResponse(
            answer=full_content,
            model="gpt-4o-mini",
            tokens_used=tokens_generated,
            persona=request.persona or "hr"
        )
    except Exception as e:
        logger.error(f"LLM Query Error: {e}")
        total_latency = time.perf_counter() - start_time
        log_latency("LLM", 0, total_latency, 0, 0, status="error")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ORCHESTRATOR (Intelligent Routing)
# =============================================================================
# OrchestratorRequest has been moved to 'binding'

@app.post("/orchestrate")
@app.post("/api/chatbot/query")
async def orchestrate_query(request: OrchestratorRequest, background_tasks: BackgroundTasks):

    logger.info(f"\n{'='*50}")
    logger.info(f"📥 RECEIVED REQUEST FROM FRONTEND")
    logger.info(f"🔎 Query: {request.query}")
    logger.info(f"👤 User ID: {request.user_id}")
    logger.info(f"🏢 Org ID: {request.org_id}")
    logger.info(f"📂 Project ID: {request.project_id}")
    logger.info(f"📝 Context: {request.context}")
    logger.info(f"{'='*50}\n")

    try:
        # --- 0. EXTRACT CONTEXT (CRITICAL FIX) ---
        # If IDs are not top-level, check if they are inside the 'context' dictionary
        if request.context:
            if not request.user_id:
                request.user_id = request.context.get("user_id")
            if not request.project_id:
                request.project_id = request.context.get("project_id")
            if not request.org_id:
                request.org_id = request.context.get("org_id")
            if not request.app_name:
                request.app_name = request.context.get("app_name")

        # 0. Fetch User Context (Personalization)
        user_context = {}
        if request.user_id and request.user_id != 'guest':
            user_context = await fetch_user_context(request.user_id)
            logger.info(f"Loaded context for user {request.user_id}: {user_context.get('name')}")
        
        # Merge explicitly provided context
        if request.context:
            user_context.update(request.context)
            
        # Fill in missing IDs from fetching
        if not request.project_id and user_context.get("project_id"):
            request.project_id = user_context.get("project_id")
        if not request.org_id and user_context.get("org_id"):
            request.org_id = user_context.get("org_id")

        # --- 🚀 LAYER 0.5: SESSION & HISTORY (Phase 2.3) ---
        session_id = f"{request.org_id}:{request.user_id}" if request.org_id else request.user_id or "anonymous"
        state = await get_shared_state_singleton()
        history = await state.get_history(session_id, user_id=request.user_id, org_id=request.org_id)
        # --- 1. DETERMINISTIC ROUTING (Hard Locking) ---
        query_lower = request.query.lower()
        target_system = None
        
        # 0.1 Check for Confirmation (Requirement 9)
        is_yes = any(w in query_lower for w in ["yes", "proceed", "confirm", "do it", "sure", "ok", "okay"])
        pending_action = None
        pending_params = None
        if request.context:
            pending_action = request.context.get("pending_action")
            pending_params = request.context.get("pending_params")

        # --- 🚀 LAYER 0.6: SEMANTIC CACHE LOOKUP (Phase 2.2) ---
        # Skip cache for confirmations or explicit commands
        if not is_yes and "@" not in request.query:
            cached_resp = await check_semantic_cache(request.query, request.org_id, request.user_id, request.project_id)
            if cached_resp:
                total_lat = time.perf_counter() - start_time
                log_latency("CACHE", 0, total_lat, 0, len(cached_resp.split()))
                return {"system": "cache", "response": cached_resp, "action": "chat"}

        if is_yes and pending_action:
            target_system = "slm"
            logger.info(f"✅ CONFIRMED: Executing pending action [{pending_action}]")
        elif any(k in query_lower for k in RAG_KEYWORDS):
            target_system = "rag"
            logger.info("🔒 INTENT LOCKED: Routing to [rag] due to RAG Keywords.")
        elif any(k in query_lower for k in SLM_KEYWORDS):
            target_system = "slm"
            logger.info("🔒 INTENT LOCKED: Routing to [slm] due to Action Keywords.")
        elif "@" in query_lower:
            target_system = "rag"
            logger.info("🔒 INTENT LOCKED: Routing to [rag] due to @mention.")
            
        # 2. SEMANTIC ROUTING (Router LLM Fallback)
        if not target_system:
            logger.info("🤖 Routing decision delegated to Orchestrator LLM...")
            try:
                # Build messages with history for context-aware routing
                router_messages = [{"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT}]
                # Add last 3 turns of history for context
                for h in history[-3:]:
                    router_messages.append(h)
                router_messages.append({"role": "user", "content": request.query})

                router_resp = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=router_messages,
                    response_format={"type": "json_object"}
                )
                router_json = json.loads(router_resp.choices[0].message.content)
                target_system = router_json.get("system", "llm").lower()
                
                # Rule 5 Enforcement: REMOVED per user request
                # No longer re-routing to [llm] if @ is missing.
            except Exception as e:
                logger.error(f"Router Error: {e}")
                target_system = "llm"
            
        logger.info(f"Orchestrator routed '{request.query}' to [{target_system}]")
        
        # 2. Route to the appropriate handler
        if target_system == "slm":
            # Call SLM with full context
            slm_context = user_context.copy()
            
            # Prepare confirmation flags
            is_confirmed = False
            p_action = None
            p_params = None
            
            if is_yes and pending_action:
                is_confirmed = True
                p_action = pending_action
                p_params = pending_params
                # We also need to pass the original query if we want to re-parse, 
                # but better to use the pending action name directly.
                # If we are confirming, the "query" can be "yes", so we need to pass the pending intent.
                query_to_send = f"Perform {pending_action} with {json.dumps(p_params)}"
            else:
                query_to_send = request.query

            slm_req = SLMQueryRequest(
                query=query_to_send,
                user_id=request.user_id,
                project_id=request.project_id,
                org_id=request.org_id,
                user_role=user_context.get("role", "employee"), 
                context=slm_context,
                is_confirmed=is_confirmed,
                pending_action=p_action,
                pending_params=p_params,
                history=history,
                app_name=request.app_name
            )
            slm_resp = await slm_chat(slm_req, background_tasks)
            
            # Save to history (Phase 2.3)
            await state.add_history(session_id, request.user_id, "user", request.query, org_id=request.org_id)
            await state.add_history(session_id, request.user_id, "assistant", slm_resp.response, org_id=request.org_id)
            
            # Add feedback request to action responses (Requirement 14)
            if slm_resp.action in ["chat", "success"]:
                slm_resp.response += "\n\n*Was this what you wanted?*"
                
            return slm_resp
            
            # slm_text = slm_resp.response if hasattr(slm_resp, 'response') else str(slm_resp)
            
            # # --- HYBRID FALLBACK ---
            # # If SLM says "NO_DATA_FOUND_IN_DB" and the query might be document-related, try RAG
            # if "NO_DATA_FOUND_IN_DB" in slm_text:
            #     logger.info("⚠️ SLM returned NO_DATA. Attempting RAG fallback...")
            #     if request.org_id:
            #         rag_req = RAGQueryRequest(
            #             question=request.query,
            #             org_id=request.org_id,
            #             project_id=request.project_id
            #         )
            #         rag_resp = await rag_query(rag_req)
                    
            #         # If RAG found something meaningful (simple heuristic)
            #         if rag_resp and "answer" in rag_resp and len(rag_resp["answer"]) > 50:
            #              logger.info("✅ RAG fallback SUCCESSFUL.")
            #              return {
            #                 "system": "rag-fallback",
            #                 "response": rag_resp.get("answer"),
            #                 "sources": rag_resp.get("sources"),
            #                 "action": "chat"
            #              }
            
            # result = {
            #     "system": "slm",
            #     "response": slm_text, 
            #     "action": "chat" 
            # }
            
            # logger.info(f"📤 SENDING RESPONSE TO FRONTEND: {result}")
            # return result

        elif target_system == "rag":
            # Extract document name from @mention
            doc_name = "general"
            if "@" in query_lower:
                parts = query_lower.split("@")
                if len(parts) > 1:
                    doc_name = parts[1].split()[0]

            rag_req = RAGQueryRequest(
                question=request.query,
                org_id=request.org_id,
                project_id=request.project_id
            )
            rag_resp = await rag_query(rag_req)
            
            # REQUIREMENT 0: SLM delivers the answer
            logger.info(f"🔍 RAG Answer received: {len(rag_resp.get('answer', ''))} chars. Sources: {rag_resp.get('sources')}")
            
            slm_context = user_context.copy()
            cleaned_query = re.sub(r'@[a-zA-Z0-9_]+', '', request.query).strip()
            
            slm_req = SLMQueryRequest(
                query=cleaned_query,
                user_id=request.user_id,
                project_id=request.project_id,
                org_id=request.org_id,
                user_role=user_context.get("role", "employee"), 
                context=slm_context,
                forced_action="present_rag",
                rag_content=rag_resp.get("answer"),
                rag_source=", ".join(rag_resp.get("sources", [])) if rag_resp.get("sources") else "Database",
                history=history
            )
            slm_resp = await slm_chat(slm_req, background_tasks)
            
            # Save to history (Phase 2.3)
            await state.add_history(session_id, request.user_id, "user", request.query, org_id=request.org_id)
            await state.add_history(session_id, request.user_id, "assistant", slm_resp.response, org_id=request.org_id)
            
            return slm_resp
            
        else:
            # Call LLM for Guardrails/Domain knowledge
            personalized_prompt = LLM_SYSTEM_PROMPT.format(
                user_name=user_context.get("name", "User"),
                user_role=user_context.get("role", "employee"),
                project_name=user_context.get("project_name", "None")
            )
            
            # Build messages with FULL history for memory
            messages = [{"role": "system", "content": personalized_prompt}]
            for h in history:
                messages.append({"role": h["role"], "content": h["content"]})
            messages.append({"role": "user", "content": request.query})
            
            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.3
            )
            llm_text = response.choices[0].message.content

            # REQUIREMENT 0: SLM delivers the answer
            slm_context = user_context.copy()
            slm_req = SLMQueryRequest(
                query=request.query,
                user_id=request.user_id,
                project_id=request.project_id,
                org_id=request.org_id,
                user_role=user_context.get("role", "employee"), 
                context=slm_context,
                forced_action="chat",
                pending_params={"llm_response": llm_text}, # Pass LLM text as parameter
                history=history
            )
            
            # In slm_chat, if action is "chat", it will look at context for answer
            # We should update slm_chat's chat handler to use this.
            slm_resp = await slm_chat(slm_req, background_tasks)
            
            # Save to history
            await state.add_history(session_id, request.user_id, "user", request.query, org_id=request.org_id)
            await state.add_history(session_id, request.user_id, "assistant", slm_resp.response, org_id=request.org_id)
            
            return slm_resp

    except Exception as e:
        logger.error(f"Orchestrator Error: {e}")
        return {"system": "error", "response": f"I encountered an error trying to process that: {str(e)}"}


# =============================================================================
# RAG ENDPOINTS (Document Ingestion & Query)
# =============================================================================
# RAGIngestRequest and RAGQueryRequest have been moved to 'binding'

# RAG utility functions (chunk_text, get_embeddings, parse_file_from_url) 
# have been moved to 'binding'

@app.post("/rag/ingest")
@app.post("/docs/ingest")
async def rag_ingest(request: RAGIngestRequest):

    try:
        # --- DB CONTEXT SWITCHING (FIX 3: centralized via select_client) ---
        app_name = (request.app_name or request.metadata.get("app_name") or "talentops").lower()
        _client_error = select_client(app_name)
        if _client_error == "COHORT_UNAVAILABLE":
            return {"success": False, "message": "The Cohort service is not currently available."}
        doc_id = request.doc_id or request.metadata.get('doc_id')
        org_id = request.org_id or request.metadata.get('org_id')
        project_id = request.project_id or request.metadata.get('project_id')
        
        if not org_id or not doc_id:
            return {"success": False, "message": "Missing org_id or doc_id"}
        
        # 1. Extract text from URL if provided
        file_text = ""
        if request.file_url:
            file_text = parse_file_from_url(request.file_url)
            
        full_text = (request.text or "") + "\n\n" + file_text
        full_text = full_text.strip()
        
        if len(full_text) < 5:
            return {"success": False, "message": "Text content too short or empty mapping"}
        
        # 2. Upsert parent document in 'documents' table
        try:
             await supabase.table("documents").insert({
                 "id": doc_id,
                 "org_id": org_id,
                 "project_id": project_id,
                 "title": request.metadata.get("title", "Uploaded Document")
             }).execute()
        except Exception as e:
             # Might fail if already exists, that's fine
             logger.info(f"Note: Document parent entry check: {e}")

        # 3. Chunk and embed
        chunks = chunk_text(full_text)
        embeddings_res = await get_embeddings(chunks)
        embeddings, embedding_latency = embeddings_res if isinstance(embeddings_res, tuple) else (embeddings_res, 0)
        
        if not chunks or not embeddings:
            return {"success": False, "message": "Failed to process document"}
        
        # Store in Supabase
        records = []
        for i, chunk in enumerate(chunks):
            records.append({
                "document_id": doc_id,
                "org_id": org_id,
                "project_id": project_id,
                "content": chunk,
                "embedding": embeddings[i]
            })
            
        # Bulk insert
        resp = await supabase.table("document_chunks").insert(records).execute()
        
        return {
            "success": True, 
            "chunks": len(chunks), 
            "message": f"Processed and stored {len(chunks)} chunks"
        }
        
    except Exception as e:
        logger.error(f"RAG Ingest Error: {e}")
        return {"success": False, "message": str(e)}

@app.post("/rag/query")
@app.post("/query")
async def rag_query(request: RAGQueryRequest):
    start_time = time.perf_counter()
    embedding_latency = 0.0
    retrieval_latency = 0.0

    try:
        # --- DB CONTEXT SWITCHING (FIX 3: centralized via select_client) ---
        app_name = (request.app_name or "talentops").lower()
        _client_error = select_client(app_name)
        if _client_error == "COHORT_UNAVAILABLE":
            return {"answer": "The Cohort service is not currently available.", "sources": []}

        # 🚀 PARALLELIZED EXECUTION BLOCK
        # We start metadata fetch and embedding generation simultaneously
        logger.info("⚡ Starting Parallel RAG Retrieval...")
        
        async def fetch_metadata():
            try:
                # Use current Supabase context
                query = supabase.table("documents").select("id, title, org_id, project_id, user_id")
                query = query.eq("org_id", request.org_id)
                
                # Filter by user_id or global (null)
                if request.user_id:
                     # Use the newly added in_ filter
                     query = query.in_("user_id", [request.user_id, "null"])
                
                resp = await query.execute()
                if resp.error:
                    # If user_id column doesn't exist yet, fallback to just org_id
                    logger.warning(f"RAG Filter Error: {resp.error}. Falling back to Org-level fetch.")
                    resp = await supabase.table("documents").select("id, title, org_id, project_id").eq("org_id", request.org_id).execute()
                return resp.data or []
            except Exception as e:
                logger.error(f"Error fetching existing doc metadata: {e}")
                return []

        # Parallelize: 1. Metadata, 2. Embedding
        metadata_task = fetch_metadata()
        embedding_task = get_embeddings([request.question])
        
        all_docs, (q_emb, emb_lat) = await asyncio.gather(metadata_task, embedding_task)
        embedding_latency = emb_lat

        # 1. Process Metadata for title matching
        doc_filters = {}
        all_doc_map = {}
        if all_docs:
            # Sort by title length descending to match longest (most specific) title first
            all_docs.sort(key=lambda x: len(x.get('title', '')), reverse=True)
            
            q_norm = re.sub(r'[^a-z0-9]', '', request.question.lower())
            logger.info(f"🔍 Normalized Query for Matching: {q_norm}")
            for d in all_docs:
                title = d.get('title', '')
                t_id = d.get('id')
                all_doc_map[t_id] = title
                t_norm = re.sub(r'[^a-z0-9]', '', title.lower())
                
                if t_norm and t_norm in q_norm:
                    doc_filters["document_id"] = t_id
                    # CRITICAL: Use the document's actual org_id for chunk fetching
                    doc_filters["org_id"] = d.get("org_id")
                    doc_filters["project_id"] = d.get("project_id")
                    logger.info(f"🎯 MATCH FOUND: '{title}' ({t_id}) matched")
                    break

        # 2. Strategy: Direct Fetch vs Vector Search
        target_doc_id = doc_filters.get("document_id")
        final_matches = []
        
        if target_doc_id:
            logger.info(f"Directly fetching chunks for Document: {target_doc_id}")
            # Use current Supabase context - and importantly, use the correct document ID and potentially ignore org_id if mismatched
            # We filter only by document_id here since it is a unique UUID
            resp = await supabase.table("document_chunks").select("content, document_id").eq("document_id", target_doc_id).execute()
            if resp.data:
                chunks = resp.data
                logger.info(f"Retrieved {len(chunks)} shards from document {target_doc_id}")
                for c in chunks:
                    final_matches.append({
                        "id": c.get('document_id'),
                        "content": c.get('content')
                    })
            
        # If no specific doc was mentioned OR direct fetch failed, use Vector Search
        if not final_matches:
            q_emb, embedding_latency = await get_embeddings([request.question])
            if q_emb:
                query_vector = q_emb[0]
                params = {
                    "query_embedding": query_vector,
                    "match_threshold": 0.01, 
                    "match_count": 20,
                    "filter": {
                        "org_id": request.org_id,
                        "project_id": request.project_id
                    }
                }
                rpc_resp = await supabase.rpc("match_documents", params)
                matches = rpc_resp.data if rpc_resp.data else []
                for m in matches:
                    final_matches.append({
                        "id": m.get('id'), # In RPC result, 'id' is the parent document ID
                        "content": m.get('content')
                    })
            else:
                return {"answer": "Failed to generate embedding", "sources": []}

        # 4. Format context with titles
        context_text = ""
        unique_sources = []
        
        # Limit to 15 chunks to avoid overwhelming context window
        for item in final_matches[:15]:
            d_id = item.get('id')
            title = all_doc_map.get(d_id, "Unknown Document")
            context_text += f"---\n[SOURCE: {title}]\n{item.get('content', '')}\n"
            unique_sources.append(title)
            
        if not context_text:
            context_text = "No relevant document sections were found in the database."

        retrieval_latency = (time.perf_counter() - start_time) - embedding_latency
        
        # 5. Return Raw Context for SLM Delivery (Requirement 0)
        return {
            "answer": context_text,
            "sources": sorted(list(set(unique_sources))),
            "metrics": {
                "embedding_latency": embedding_latency,
                "retrieval_latency": retrieval_latency,
                "total_rag_latency": time.perf_counter() - start_time
            }
        }
        
    except Exception as e:
        logger.error(f"RAG Query Error: {e}")
        return {
            "answer": "Error processing query", 
            "sources": [], 
            "error": str(e),
            "metrics": {"embedding_latency": 0.0, "retrieval_latency": 0.0}
        }

# =============================================================================
# STARTUP
# =============================================================================
@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("Modal Gateway - Unified Server v2.0")
    logger.info(f"Running on port {PORT}")
    logger.info("=" * 60)
    logger.info("Available endpoints:")
    logger.info("  GET  /              - Root")
    logger.info("  GET  /health        - Health check")
    logger.info("  POST /slm/chat      - SLM Chatbot")
    logger.info("  POST /llm/query     - OpenAI LLM")
    logger.info("  POST /rag/query     - RAG Query")
    logger.info("  POST /rag/ingest    - RAG Ingest")
    logger.info("=" * 60)

if __name__ == "__main__":
    print("=" * 60)
    print("Modal Gateway - Unified Server v2.0")
    print(f"Starting on http://0.0.0.0:{PORT}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
