"""
app/routers/health.py
=====================
Health check endpoints — lightweight, no DB calls required.
Extracted from unified_server.py (lines 376-394).
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.config import PORT

router = APIRouter(tags=["Health"])


@router.get("/health")
@router.get("/api/health")
@router.get("/slm/health")
async def health():
    return JSONResponse({
        "status": "ok",
        "message": "ModalGateway Unified Server is running",
        "port": PORT,
        "backends": ["SLM", "LLM", "RAG"],
        "version": "3.0.0"
    })
