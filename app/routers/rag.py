"""
app/routers/rag.py
==================
RAG (Retrieval-Augmented Generation) endpoints.
Extracted from unified_server.py RAG section.
"""
from fastapi import APIRouter, BackgroundTasks
from binding import RAGIngestRequest, RAGQueryRequest

router = APIRouter(prefix="/rag", tags=["RAG"])

# NOTE: RAG route implementations are registered in app/main.py
# until they are fully extracted:
#   - POST /rag/ingest  → ingest documents into vector DB
#   - POST /rag/query   → semantic query against vector DB
#   - GET  /rag/health  → RAG backend health check
