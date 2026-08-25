"""
AutoReconAI - Agent 2: DomainReasonerAI (SentinelRouterAI)
===========================================================
Role: Domain Context Reasoner, Query Rewriter/Enricher, Intent Tagger & Data Dependency Evaluator.
- Injected with domain architecture: 3 uploaded file schemas, virtual 3-way matrix join, and 3 commercial edge cases.
- Explicitly declares required datasets in `data_requirements` for downstream gating.
- Cleans and enriches raw user queries (fixing typos, de-noising slang, resolving pronouns from chat history) WITHOUT hallucinating unrequested actions.
- Anti-Guessing Rule: If conversational pronouns cannot be resolved with high confidence from explicit history, preserves ambiguity.
- Outputs structured intent, tags, confidence score, and data requirements.
"""

import os
import re
import json
import requests
import traceback
import dotenv

dotenv.load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
CANDIDATE_MODELS = ["gemini-3-flash-preview", "gemini-3.1-pro-preview", "gemini-3.1-flash-lite-preview", "gemini-flash-latest"]

DOMAIN_REASONER_SYSTEM_PROMPT = """You are DomainReasonerAI — the Domain Intelligence, Query Enrichment, and Dependency Planning AI Agent for AutoReconAI.

SYSTEM DOMAIN & DATASET ARCHITECTURE:
AutoReconAI performs an automated 3-way financial reconciliation across 3 core merchant files:

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
2. MDR Fee Overcharges: Gateway billed MDR fee rate exceeds contracted SLA in config.ini (Standard: 2.00% MDR + 18% GST = 2.36% effective). (Action: 100% cash-recoverable claim against Razorpay).
3. Orphan Customer Refunds: Settlement contains negative net credit entries (-₹1,200) for prior-period returns (`ORD_PRIOR_xxx`) not in current store orders. (Action: Internal ERP ledger adjustment).

4. GATEWAY DATABASE:
   - Core 'payments' table in SQLite DB (`store.db`) can be inspected for payment_id, order_id, status, settlement_utr. Merchant store tables (orders/cart) are private client data and not accessible in gateway DB.

YOUR TASKS:
1. QUERY REWRITING & ENRICHMENT (De-noising):
   - Analyze raw user query (correcting typos, slang, abbreviations like "y r sum ords pending", "wat happnd to ord 1002", "how mch can i clame").
   - Resolve pronouns or references ("it", "this order", "that transaction", "why is it pending") strictly from the EXPLICIT RECENT CONVERSATION HISTORY provided.
   - ANTI-GUESSING RULE: If an entity reference cannot be resolved with high confidence from history, preserve ambiguity instead of guessing or inventing an order ID.
   - STRICT CONSTRAINT: Never add unrequested actions. If user asks "what is ORD_1002 fee?", rewrite as "What is the fee charged and reconciliation status for order ORD_1002?" — do NOT add instructions to draft dispute tickets or generate full audit reports.

2. DECLARE DATA REQUIREMENTS (`data_requirements`):
   - List the exact files needed to fulfill this request:
     * Full audit / Match rate / Dropped webhooks -> `["store_orders.csv", "razorpay_settlement_recon.csv", "bank_statement"]`
     * Fee overcharges / Recoverable amount / Dispute ticket -> `["razorpay_settlement_recon.csv"]`
     * Specific Order Trace -> `["store_orders.csv", "razorpay_settlement_recon.csv", "bank_statement"]`
     * Gateway Database query -> `["gateway_db"]`
     * General finance / Tax formulas -> `[]`

3. INTENT CLASSIFICATION:
   - "POINT_METRIC_QUERY" -> Specific single number/metric (e.g. total recoverable money, match rate, total GMV).
   - "SINGLE_ORDER_TRACE" -> Deep 3-way trace of a specific Order ID.
   - "DISPUTE_CLAIM" -> Drafting official Razorpay merchant dispute ticket for fee overcharges.
   - "COMPREHENSIVE_AUDIT" -> Full audit report / executive breakdown of all mismatches and edge cases.
   - "GATEWAY_DB_QUERY" -> Inspecting Razorpay gateway database table ('payments').

4. OUTPUT CONFIDENCE & METADATA:
   - Provide a confidence score (0.0 to 1.0) and list any missing information.

Always respond ONLY in valid JSON matching this schema:
{
  "enriched_query": "string",
  "intent": "POINT_METRIC_QUERY" | "SINGLE_ORDER_TRACE" | "DISPUTE_CLAIM" | "COMPREHENSIVE_AUDIT" | "GATEWAY_DB_QUERY",
  "tags": ["string"],
  "extracted_entities": {
    "order_id": "string or null",
    "category": "fee_overcharge | dropped_webhook | orphan_refund | null"
  },
  "data_requirements": ["store_orders.csv" | "razorpay_settlement_recon.csv" | "bank_statement" | "gateway_db"],
  "confidence": 0.95,
  "missing_information": ["string"],
  "summary": "string"
}
"""

from config_loader import GatewayConfig


class DomainReasonerAI:
    """Agent 2: Domain Intelligence, Query Enrichment, Entity Extraction & Data Dependency Evaluator."""

    @staticmethod
    def classify_and_tag(user_query: str, session_data: dict = None, chat_history: list = None) -> dict:
        if not API_KEY:
            return DomainReasonerAI._heuristic_fallback(user_query, chat_history)

        session_data = session_data or {}
        orders_count = len(session_data.get("orders", []))
        settlements_count = len(session_data.get("settlements", []))
        bank_count = len(session_data.get("bank_txns", []))

        ingestion_context = (
            f"\nACTIVE SESSION DATASET STATE:\n"
            f"- Contracted SLA Terms (from config.ini): {GatewayConfig.get_sla_text()}\n"
            f"- Loaded Store Orders Count: {orders_count}\n"
            f"- Loaded Settlement Records Count: {settlements_count}\n"
            f"- Loaded Bank Transactions Count: {bank_count}\n"
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
            history_context = "\nEXPLICIT RECENT CONVERSATION HISTORY (Last 5 Interactions):\n" + "\n".join(history_lines) + "\n"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{DOMAIN_REASONER_SYSTEM_PROMPT}{ingestion_context}{history_context}\nRAW MERCHANT USER QUERY:\n\"{user_query}\""}]
                }
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
                    parsed = json.loads(text)
                    return {
                        "scope": "IN_SCOPE",
                        "enriched_query": parsed.get("enriched_query", user_query),
                        "intent": parsed.get("intent", "COMPREHENSIVE_AUDIT"),
                        "tags": parsed.get("tags", []),
                        "extracted_entities": parsed.get("extracted_entities", {}),
                        "data_requirements": parsed.get("data_requirements", []),
                        "confidence": float(parsed.get("confidence", 0.95)),
                        "missing_information": parsed.get("missing_information", []),
                        "summary": parsed.get("summary", user_query)
                    }
                elif resp.status_code == 429:
                    continue
            except Exception:
                continue

        return DomainReasonerAI._heuristic_fallback(user_query, chat_history)

    @staticmethod
    def _heuristic_fallback(query: str, chat_history: list = None) -> dict:
        q = query.lower()

        # Extract order ID directly or resolve from chat history
        oid_match = re.search(r'\b(ord_?(?:prior_)?\d+)\b', q)
        extracted_oid = oid_match.group(1).upper().replace("ORD", "ORD_") if oid_match else None

        if not extracted_oid and chat_history and any(w in q for w in ["it", "this", "that", "improper", "why", "what is"]):
            for turn in reversed(chat_history):
                hist_text = f"{turn.get('user', '')} {turn.get('assistant', '')}".lower()
                hist_oid_match = re.search(r'\b(ord_?(?:prior_)?\d+)\b', hist_text)
                if hist_oid_match:
                    extracted_oid = hist_oid_match.group(1).upper().replace("ORD", "ORD_")
                    break

        intent = "COMPREHENSIVE_AUDIT"
        tags = ["#reconciliation_audit"]
        data_reqs = ["store_orders.csv", "razorpay_settlement_recon.csv", "bank_statement"]
        enriched_query = query

        if extracted_oid:
            intent = "SINGLE_ORDER_TRACE"
            tags = [f"#{extracted_oid.lower()}", "#order_trace"]
            enriched_query = f"Inspect and trace the 3-way reconciliation lifecycle for order {extracted_oid} across Store, Gateway, and Bank statement."
            data_reqs = ["store_orders.csv", "razorpay_settlement_recon.csv", "bank_statement"]
        elif any(k in q for k in ["recover", "how much", "match rate", "total fee", "lost", "claimable"]):
            intent = "POINT_METRIC_QUERY"
            tags = ["#point_metric", "#recoverable_amount"]
            enriched_query = "Calculate the total recoverable money and MDR fee overcharges from Razorpay."
            data_reqs = ["razorpay_settlement_recon.csv"]
        elif any(k in q for k in ["dispute", "ticket", "claim", "draft claim"]):
            intent = "DISPUTE_CLAIM"
            tags = ["#dispute_claim", "#fee_overcharge"]
            enriched_query = "Draft an official Razorpay Merchant Dispute Claim Ticket for all detected MDR fee overcharges."
            data_reqs = ["razorpay_settlement_recon.csv"]
        elif any(k in q for k in ["gateway db", "payments table", "database"]):
            intent = "GATEWAY_DB_QUERY"
            tags = ["#gateway_db"]
            enriched_query = "Query the Razorpay gateway payments database table."
            data_reqs = ["gateway_db"]

        return {
            "scope": "IN_SCOPE",
            "enriched_query": enriched_query,
            "intent": intent,
            "tags": tags,
            "extracted_entities": {"order_id": extracted_oid, "category": None},
            "data_requirements": data_reqs,
            "confidence": 0.90,
            "missing_information": [],
            "summary": query
        }


# Backward compatibility alias
SentinelRouterAI = DomainReasonerAI
