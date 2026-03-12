-- 1. ENABLE VECTOR EXTENSION (Required for Semantic Search)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. CREATE SEMANTIC CACHE TABLE
CREATE TABLE IF NOT EXISTS semantic_cache (
    id BIGSERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,
    query_embedding vector(1536), -- Assuming OpenAI/Together 1536-dim embeddings
    response_text TEXT NOT NULL,
    org_id TEXT,
    user_id TEXT,
    project_id TEXT,
    user_role TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. CREATE SEMANTIC MATCH FUNCTION (RPC)
-- This function allows the chatbot to find similar previously-answered questions.
CREATE OR REPLACE FUNCTION match_semantic_cache (
  query_embedding vector(1536),
  match_threshold float,
  match_count int,
  msg_org_id text default null,
  msg_user_id text default null,
  msg_project_id text default null
)
RETURNS TABLE (
  id bigint,
  query_text text,
  response_text text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    sc.id,
    sc.query_text,
    sc.response_text,
    1 - (sc.query_embedding <=> match_semantic_cache.query_embedding) AS similarity
  FROM semantic_cache sc
  WHERE 
    (msg_org_id IS NULL OR sc.org_id = msg_org_id) AND
    (msg_user_id IS NULL OR sc.user_id IS NULL OR sc.user_id = msg_user_id) AND
    (msg_project_id IS NULL OR sc.project_id = msg_project_id) AND
    1 - (sc.query_embedding <=> match_semantic_cache.query_embedding) > match_threshold
  ORDER BY sc.query_embedding <=> match_semantic_cache.query_embedding
  LIMIT match_count;
END;
$$;

-- 4. CREATE CHAT HISTORY TABLE (Fallback for Redis)
CREATE TABLE IF NOT EXISTS chat_history (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    org_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. INDEXES FOR PERFORMANCE
CREATE INDEX IF NOT EXISTS chat_history_session_idx ON chat_history (session_id, user_id);
