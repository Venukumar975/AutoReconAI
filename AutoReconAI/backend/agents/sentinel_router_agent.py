"""
AutoReconAI - Agent 2: SentinelRouterAI
========================================
Role: Scope Guardrail & Granular Intent Classifier Agent.
- Enforces strict domain boundaries (Finance, 3-way reconciliation, PG fees, dispute claims).
- Classifies queries into granular intents (POINT_METRIC_QUERY, SINGLE_ORDER_TRACE, DISPUTE_CLAIM, COMPREHENSIVE_AUDIT, GATEWAY_DB_QUERY).
- Extracts structured intent tags and order IDs.
- Fully dynamic and dataset-agnostic.
"""

import os
import re
import json
import requests
import traceback
import dotenv

dotenv.load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
CANDIDATE_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]

ROUTER_SYSTEM_PROMPT = """You are DomainReasonerAI (SentinelRouterAI) — the Domain Intelligence, Scope Guardrail, Contextual Memory, and Intent Classification AI Agent for AutoReconAI.

SYSTEM DOMAIN & DATASET ARCHITECTURE:
AutoReconAI performs automated 3-way financial reconciliation across 3 core merchant files:

1. FILE 1: Store Orders Ledger (`store_orders.csv`)
   - Schema Fields: `order_id`, `customer_name`, `gross_amount`, `order_status` ('FULFILLED' or 'PENDING'), `created_at`.
   - Role: Merchant's internal e-commerce sales ledger.

2. FILE 2: Razorpay Settlement Payout Ledger (`razorpay_settlement_recon.csv`)
   - Schema Fields: `settlement_id`, `settlement_utr`, `payment_id`, `order_id`, `amount`, `fee`, `tax`, `net_credit`, `type`, `status` ('captured'), `created_at`, `settled_at`.
   - Role: Payment gateway transaction ledger detailing billed MDR fees and net payouts grouped by settlement UTR.

3. FILE 3: Bank Statement Ledger (`bank_statement_union_bank.pdf` or `.xlsx`)
   - Schema Fields: `txn_date`, `description` (narration with UTR), `extracted_utr`, `debit`, `credit`, `balance`, `is_gateway_credit`.
   - Role: Verifies actual net deposits received in merchant's bank account for each settlement batch UTR.

VIRTUAL 3-WAY RECONCILIATION MATRIX:
The 3 files are joined into a unified virtual reconciliation table:
- Bank Deposit Credit is linked to Settlement Payouts via matching `settlement_utr`.
- Store Orders are joined with Gateway Settlements on `order_id`.

3 CORE COMMERCIAL EDGE CASES:
1. Dropped Webhooks: Gateway status 'captured' and settled to bank, but store order status 'PENDING'. (Action: fulfill manually, ₹0.00 cash claim from PG).
2. MDR Fee Overcharges: Gateway billed MDR fee rate exceeds contracted SLA in config.ini (Action: 100% cash-recoverable claim against Razorpay).
3. Orphan Customer Refunds: Settlement contains negative net credit entries (-₹1,200) for prior-period returns (`ORD_PRIOR_xxx`) not in current store orders. (Action: Internal ERP ledger adjustment).

4. GATEWAY DATABASE:
   - Core 'payments' table in SQLite DB (`store.db`) can be inspected for payment_id, order_id, status, settlement_utr. Merchant store tables (orders/cart) are private client data and not accessible in gateway DB.

INSTRUCTIONS:
1. Analyze the user query carefully (handling typos, slang, and abbreviations like "y r sum ordrs mismached", "wat happnd to ord 1002", "recoverable money").
2. Check if the query is IN_SCOPE (finance, reconciliation, orders, payments, fees, bank deposits, GST tax math, dispute claims, gateway DB) or OUT_OF_SCOPE (movies, cooking, sports, code in other fields, casual personal chat).
   - NOTE: Polite greetings or courtesy closings (e.g., "thank you", "thanks", "hello", "hi", "ok got it") are IN_SCOPE. For these, set "intent": "COURTESY" and provide a warm helpful 1-line response.
3. If OUT_OF_SCOPE:
   - Set "scope": "OUT_OF_SCOPE"
   - Provide a simple, polite 1-line response in "guardrail_message": "Sorry, I can only assist with financial reconciliation, gateway fee audits, and settlement disputes."
4. If IN_SCOPE:
   - Set "scope": "IN_SCOPE"
   - Set "intent" to the most precise category:
     * "POINT_METRIC_QUERY" -> When user asks for a specific number, single metric, or targeted amount (e.g. "what is the total recoverable money", "what is our match rate", "how much was overcharged").
     * "SINGLE_ORDER_TRACE" -> When user asks about a specific Order ID (e.g. "what happened to ORD_1002", "why is ORD_1004 pending").
     * "DISPUTE_CLAIM" -> When user asks to draft/prepare an official dispute ticket or chargeback claim.
     * "COMPREHENSIVE_AUDIT" -> When user asks for a full breakdown, complete report, or executive summary of all mismatches.
     * "GATEWAY_DB_QUERY" -> When user asks to inspect the Razorpay gateway payments database table.
     * "COURTESY" -> For simple "thank you", "thanks", "hi", "hello" messages.
   - Extract relevant "#tags" list (e.g. ["#recoverable_amount", "#fee_overcharge", "#ord_1002", "#dropped_webhook", "#tax_calculation", "#gst_details"]).
   - Extract "extracted_entities": {"order_id": "ORD_xxxx or null", "category": "fee_overcharge | dropped_webhook | orphan_refund | null"}.
   - Provide a clean 1-line "summary" of the request.
5. MULTI-TURN REFERENCE RESOLUTION & ANTI-HALLUCINATION:
   - If the user query is a follow-up, clarification, or uses pronouns/references like 'it', 'this', 'that', 'why is it', 'is this improper', resolve the target entity (such as order_id) from the RECENT CONVERSATION HISTORY.
   - CRITICAL ANTI-HALLUCINATION RULE: If the previous interaction was a general audit summary or batch list containing multiple orders, DO NOT randomly pick an order ID from that list when the user asks a high-level question ("did I lose money?", "how much is recoverable?"). Set "order_id": null.

Always respond ONLY in valid JSON matching this schema:
{
  "scope": "IN_SCOPE" | "OUT_OF_SCOPE",
  "guardrail_message": "string",
  "intent": "POINT_METRIC_QUERY" | "SINGLE_ORDER_TRACE" | "DISPUTE_CLAIM" | "COMPREHENSIVE_AUDIT" | "GATEWAY_DB_QUERY" | "COURTESY",
  "tags": ["string"],
  "extracted_entities": {
    "order_id": "string or null",
    "category": "string or null"
  },
  "summary": "string"
}
"""


from config_loader import GatewayConfig

class SentinelRouterAI:
    """Agent 2: Evaluates scope, classifies intent, and tags user queries."""

    @staticmethod
    def classify_and_tag(user_query: str, session_data: dict = None, chat_history: list = None) -> dict:
        if not API_KEY:
            return SentinelRouterAI._heuristic_fallback(user_query, chat_history)

        session_data = session_data or {}
        orders_count = len(session_data.get("orders", []))
        settlements_count = len(session_data.get("settlements", []))
        bank_count = len(session_data.get("bank_txns", []))

        ingestion_context = (
            f"\nINGESTION SESSION STATE:\n"
            f"- Active Contracted SLA Terms (from config.ini): {GatewayConfig.get_sla_text()}\n"
            f"- Store Orders Count: {orders_count}\n"
            f"- Settlement Records Count: {settlements_count}\n"
            f"- Bank Transactions Count: {bank_count}\n"
        )

        history_context = ""
        if chat_history:
            history_lines = []
            for idx, turn in enumerate(chat_history[-5:], 1):
                u_text = turn.get("user", "")
                a_text = turn.get("assistant", "")
                if len(a_text) > 160:
                    a_text = a_text[:160] + "..."
                history_lines.append(f"[Turn {idx}] User: \"{u_text}\" -> Assistant: \"{a_text}\"")
            history_context = "\nRECENT CONVERSATION HISTORY (Last 5 Interactions):\n" + "\n".join(history_lines) + "\n"

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{ROUTER_SYSTEM_PROMPT}{ingestion_context}{history_context}\nCURRENT USER QUERY:\n{user_query}"}]}
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

        return SentinelRouterAI._heuristic_fallback(user_query, chat_history)

    @staticmethod
    def _heuristic_fallback(query: str, chat_history: list = None) -> dict:
        q = query.lower()
        if any(w in q for w in ["thank you", "thanks", "thx", "thnak you", "appreciate it"]):
            return {
                "scope": "IN_SCOPE",
                "guardrail_message": "You're very welcome! Let me know if you need any further analysis on your transactions or dispute claims.",
                "intent": "COURTESY",
                "tags": ["#courtesy"],
                "extracted_entities": {"order_id": None, "category": None},
                "summary": "Courtesy message"
            }

        out_of_scope_keywords = ["recipe", "iron man", "movie", "weather", "song", "joke", "capital of", "who is", "cooking", "actor"]
        finance_keywords = ["order", "payment", "recon", "fee", "dispute", "bank", "settle", "utr", "mismatch", "mdr", "gst", "db", "table", "recover", "lost"]

        if any(w in q for w in out_of_scope_keywords) and not any(f in q for f in finance_keywords):
            return {
                "scope": "OUT_OF_SCOPE",
                "guardrail_message": "Sorry, I can only assist with financial reconciliation, gateway fee audits, and settlement disputes.",
                "intent": "OUT_OF_SCOPE",
                "tags": ["#out_of_scope"],
                "extracted_entities": {"order_id": None, "category": None},
                "summary": "Out of scope request"
            }

        oid_match = re.search(r'\b(ord_?(?:prior_)?\d+)\b', q)
        extracted_oid = oid_match.group(1).upper().replace("ORD", "ORD_") if oid_match else None

        # Resolve entity from chat_history if query uses pronouns
        if not extracted_oid and chat_history and any(w in q for w in ["it", "this", "that", "improper", "why", "what is"]):
            for turn in reversed(chat_history):
                hist_text = f"{turn.get('user', '')} {turn.get('assistant', '')}".lower()
                hist_oid_match = re.search(r'\b(ord_?(?:prior_)?\d+)\b', hist_text)
                if hist_oid_match:
                    extracted_oid = hist_oid_match.group(1).upper().replace("ORD", "ORD_")
                    break

        intent = "COMPREHENSIVE_AUDIT"
        tags = ["#reconciliation_audit"]

        if extracted_oid:
            intent = "SINGLE_ORDER_TRACE"
            tags = [f"#{extracted_oid.lower()}", "#order_trace"]
        elif "recover" in q or "how much" in q or "match rate" in q or "total fee" in q or "lost" in q:
            intent = "POINT_METRIC_QUERY"
            tags = ["#point_metric", "#recoverable_amount"]
        elif "dispute" in q or "ticket" in q or "claim" in q:
            intent = "DISPUTE_CLAIM"
            tags = ["#fee_overcharge", "#razorpay_dispute"]
        elif "gateway db" in q or "payments table" in q:
            intent = "GATEWAY_DB_QUERY"
            tags = ["#gateway_db"]

        return {
            "scope": "IN_SCOPE",
            "guardrail_message": "",
            "intent": intent,
            "tags": tags,
            "extracted_entities": {"order_id": extracted_oid, "category": None},
            "summary": query
        }
