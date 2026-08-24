"""
AutoReconAI - Agent 0: IngestionAuditorAI
==========================================
Role: First-line Data Readiness & Ingestion Auditor Agent powered by Gemini.
- Evaluates whether the user's query requires live uploaded reconciliation ledgers.
- Inspects which of the 3 financial files are uploaded vs missing in the session.
- If files are missing, generates structured guidance instead of empty 0-data tables.
- If data is ready or query is for gateway DB / general finance, approves execution to proceed.
"""

import os
import json
import requests
import traceback
import dotenv

dotenv.load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
CANDIDATE_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]

INGESTION_AUDITOR_PROMPT = """You are IngestionAuditorAI — the First-Stage Data Ingestion & Dataset Readiness AI Agent for AutoReconAI.

YOUR ROLE:
Before any financial reconciliation audit begins, inspect the merchant's live uploaded dataset status in this session:
1. Store Orders Ledger (Merchant CSV)
2. Bank Statement Ledger (Union Bank PDF/Excel)
3. Razorpay Settlement Ledger (PG Payout CSV)

RULES:
1. If the user query is asking for reconciliation analysis, mismatch auditing, fee discrepancies, or dispute claims, but financial files are missing in this session:
   - Set "ready": false
   - Set "status": "INGESTION_REQUIRED"
   - Generate a clear, friendly, structured message in "message" explaining which files are uploaded vs missing, and guide them to upload the missing files in the Data Ingestion Hub.
2. If the user query is about the Razorpay Gateway Core DB ('payments' table), general financial SLA terms, or out-of-scope queries:
   - Set "ready": true (allow request to proceed to SentinelRouterAI).
3. If all 3 files are present in the session:
   - Set "ready": true.

Always respond ONLY in valid JSON matching this schema:
{
  "ready": true | false,
  "status": "DATA_READY" | "INGESTION_REQUIRED",
  "missing_files": ["string"],
  "uploaded_files": ["string"],
  "message": "string"
}
"""


class IngestionAuditorAI:
    """Agent 0: Audits dataset ingestion readiness."""

    @staticmethod
    def audit_ingestion_readiness(user_query: str, session_data: dict) -> dict:
        orders = session_data.get("orders", [])
        settlements = session_data.get("settlements", [])
        bank_txns = session_data.get("bank_txns", [])

        orders_count = len(orders)
        settlements_count = len(settlements)
        bank_count = len(bank_txns)

        if orders_count > 0 and settlements_count > 0 and bank_count > 0:
            return {"ready": True, "status": "DATA_READY"}

        if not API_KEY:
            return IngestionAuditorAI._fallback_reasoning(user_query, orders_count, settlements_count, bank_count)

        context_prompt = (
            f"{INGESTION_AUDITOR_PROMPT}\n\n"
            f"LIVE INGESTION STATUS IN THIS SESSION:\n"
            f"- Store Orders Ledger Count: {orders_count}\n"
            f"- Bank Statement Transactions Count: {bank_count}\n"
            f"- Razorpay Settlement Records Count: {settlements_count}\n\n"
            f"MERCHANT USER QUERY: {user_query}"
        )

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": context_prompt}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }

        for model in CANDIDATE_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
            try:
                resp = requests.post(url, json=payload, timeout=25)
                if resp.status_code == 200:
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text)
                elif resp.status_code == 429:
                    continue
            except Exception:
                continue

        return IngestionAuditorAI._fallback_reasoning(user_query, orders_count, settlements_count, bank_count)

    @staticmethod
    def _fallback_reasoning(query: str, orders_cnt: int, settlements_cnt: int, bank_cnt: int) -> dict:
        q = query.lower()
        if any(k in q for k in ["gateway db", "payment", "payments table", "iron man", "recipe", "weather", "movie"]):
            return {"ready": True, "status": "DATA_READY"}

        missing = []
        uploaded = []
        if orders_cnt == 0: missing.append("Store Orders CSV (Step 1)")
        else: uploaded.append("Store Orders CSV")

        if bank_cnt == 0: missing.append("Bank Statement PDF/Excel (Step 2)")
        else: uploaded.append("Bank Statement")

        if settlements_cnt == 0: missing.append("Razorpay Settlement CSV (Step 3)")
        else: uploaded.append("Razorpay Settlement CSV")

        if not missing:
            return {"ready": True, "status": "DATA_READY"}

        missing_bullets = "\n".join([f"- 📄 **{m}**" for m in missing])
        msg = (
            f"⚠️ **Data Ingestion Required**\n\n"
            f"To perform reconciliation analysis and investigate transactions, please upload your dataset files in the **Data Ingestion Hub**:\n\n"
            f"**Missing Files:**\n{missing_bullets}\n\n"
            f"Once uploaded, our agent pipeline will audit all transactions and fee variances in real time."
        )
        return {
            "ready": False,
            "status": "INGESTION_REQUIRED",
            "missing_files": missing,
            "uploaded_files": uploaded,
            "message": msg
        }
