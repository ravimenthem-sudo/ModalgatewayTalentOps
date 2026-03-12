# Hybrid SLM/LLM Architecture & Model Provenance Guide

## 1. Project Objective
The goal of this implementation was to achieve **Small Language Model (SLM) Finality**. This means that although a Large Language Model (LLM) may be used for internal drafting or reasoning, the **final response** delivered to the user is strictly synthesized and sent by the SLM (**Meta-Llama-3.1-8B**). 

This approach combines the "professional drafting" capabilities of an LLM with the "deterministic delivery" and compliance of an SLM, and provides clear **Model Provenance** (proof of origin) for the team lead and management.

---

## 2. Technical Architecture Overview

The system uses a **Two-Step Hybrid Pipeline** for every chatbot interaction:

### Phase A: Intent & Planning (SLM)
- **Model:** Meta-Llama-3.1-8B-Instruct-Turbo
- **Task:** The SLM parses the user's natural language to identify the "Action" (e.g., `get_tasks`, `get_attendance`) and extracts parameters.

### Phase B: Data Retrieval
- **Task:** The system fetches real-time data from the **Supabase** database based on the SLM's instructions.

### Phase C: Professional Drafting (LLM Internal)
- **Model:** GPT-4o-mini
- **Task:** Using the retrieved data, the LLM creates a professional, HR-compliant draft response. This draft is **hidden** from the user.

### Phase D: Final Synthesis (SLM Final)
- **Model:** **Meta-Llama-3.1-8B-Instruct-Turbo**
- **Task:** The SLM takes the professional draft and re-synthesizes it into the **Final Response**. This ensures the SLM is the definitive "last speaker" in the chain.

---

## 3. Implementation Details

### A. Data Layer (`binding/models.py`)
We added transparency fields to the `SLMQueryResponse` to expose model origin in the API metadata:
```python
class SLMQueryResponse(BaseModel):
    response: str
    action: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    intent_model: str  # e.g., "Meta-Llama-3.1-8B-Instruct-Turbo (SLM)"
    synthesis_model: str # e.g., "Meta-Llama-3.1-8B-Instruct-Turbo (SLM)"
```

### B. Gateway Layer (`unified_server.py`)
The `slm_chat` function was refactored from a single LLM call into a two-step process to enforce SLM-finality. 
- **Step 1:** Call `openai_client` for the `professional_draft`.
- **Step 2:** Call `together_client` (Llama 8B) with the draft to generate the `final_response`.

---

## 4. How to Verify & Provide Proof

A dedicated verification tool `verify_models.py` was created to provide "Provenance Evidence" in the command prompt.

### 📜 Execution Command:
```powershell
py verify_models.py "Show me my tasks"
```

### 🔍 Proof of Model Origin:
The output will clearly state:
1. **INTENT PARSING (SLM):** Meta-Llama-3.1-8B-Instruct-Turbo (SLM)
2. **RESPONSE SYNTHESIS (SLM):** Meta-Llama-3.1-8B-Instruct-Turbo (SLM)

This demonstrates to management that the SLM is responsible for the final user communication.

---

## 5. Scope of Coverage
The SLM-final logic is active across the entire system:
1. **HR Modules:** Tasks, Attendance, Leaves, and Analytics.
2. **Knowledge Base (RAG):** Answers from uploaded documents.
3. **Internal Navigation:** Routing the user between dashboard pages.
4. **General Assistance:** Friendly chat and support queries.

---

## 6. Maintenance Guide for Developers
To modify the output tone or rules:
1. Locate the `slm_final_prompt` variable inside the `slm_chat` function in `unified_server.py`.
2. Ensure the `synthesis_model` field in the response remains pointed to `together_client` (Llama 8B) to maintain SLM-finality compliance.

---
**Summary for Management:** 
The platform is now 100% compliant with SLM-final response requirements, ensuring data-backed accuracy with a professional tone while proving model origin at every step.
