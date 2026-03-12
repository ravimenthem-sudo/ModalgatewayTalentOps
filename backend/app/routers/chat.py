"""
app/routers/chat.py
====================
SLM Chat router — /slm/chat endpoint.
This thin router receives the request, runs RBAC, calls the core chat pipeline,
and returns the response. All business logic stays in the unified pipeline for now.
Extracted and delegating to: unified_server.slm_chat (backward compatible)
"""
from fastapi import APIRouter, BackgroundTasks
from binding import SLMQueryRequest, SLMQueryResponse

router = APIRouter(tags=["SLM Chat"])

# NOTE: The /slm/chat endpoint is registered directly in app/main.py
# because it contains the full 1300-line pipeline. This file is the
# placeholder for when that pipeline gets further decomposed into:
#   - app/services/intent_classifier.py
#   - app/services/response_synthesizer.py
#   - app/services/task_service.py
#   - app/services/attendance_service.py
#   - app/services/leave_service.py
#   etc.
