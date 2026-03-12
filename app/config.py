"""
app/config.py
=============
Centralized configuration for ModalGateway.
All environment variables are loaded here — import from this module everywhere.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# === AI Providers ===
TOGETHER_API_KEY: str = os.getenv("TOGETHER_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# === TalentOps Database ===
TALENTOPS_SUPABASE_URL: str = os.getenv("TALENTOPS_SUPABASE_URL", "")
TALENTOPS_SERVICE_ROLE_KEY: str = os.getenv("TALENTOPS_SUPABASE_SERVICE_ROLE_KEY", "")

# === Cohort Database ===
COHORT_SUPABASE_URL: str = os.getenv("COHORT_SUPABASE_URL", "")
COHORT_SERVICE_ROLE_KEY: str = os.getenv("COHORT_SUPABASE_SERVICE_ROLE_KEY", "")

# === Redis ===
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

# === Server ===
PORT: int = int(os.getenv("PORT", 8035))

# === AI Models ===
INTENT_MODEL: str = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
SYNTHESIS_MODEL: str = "gpt-4o-mini"

# === Rate Limiter Settings ===
RATE_LIMIT_CAPACITY: int = 10
RATE_LIMIT_REFILL_RATE: float = 0.5  # tokens per second
