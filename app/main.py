"""
app/main.py
============
ModalGateway — Thin FastAPI Application Entry Point
====================================================
This file ONLY:
  1. Creates the FastAPI app
  2. Adds middleware (CORS, logging)
  3. Registers routers
  4. Mounts the startup lifecycle

All business logic lives in:
  - app/services/         (intent classifier, data fetchers, synthesizer)
  - app/routers/          (route handlers)
  - app/state.py          (rate limiter, session history)
  - app/config.py         (all environment variables)

The heavy slm_chat pipeline is imported from unified_server
until it is fully decomposed in Phase 2 of refactoring.
"""

import logging
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import PORT
from app.routers import health
from app.state import get_shared_state_singleton

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Create Application
# ─────────────────────────────────────────────
app = FastAPI(
    title="ModalGateway Unified API",
    description="TalentOps AI Chatbot Backend — SLM + LLM + RAG",
    version="3.0.0"
)

# ─────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # TODO: Replace with frontend URL after Fix 2
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Register Routers
# ─────────────────────────────────────────────
app.include_router(health.router)

# Chat, RAG, and LLM routes are still served from unified_server.py
# They will be migrated here incrementally as each service module is extracted.

# ─────────────────────────────────────────────
# Startup Event
# ─────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    logger.info("ModalGateway app/main.py starting up...")
    await get_shared_state_singleton()
    logger.info("Shared state initialized.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
