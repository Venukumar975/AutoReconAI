"""
AutoReconAI - Agent 4: PrecisionSynthesizerAI
==============================================
Role: Pure Presentation Formatter, Question-Answer Alignment & Precision Editor Agent.
- Takes: Enriched Query + Tags from DomainReasonerAI + Live Verified Tool Data from ReconAuditorAI + 5-Turn Memory Window.
- Strictly enforces Zero Boilerplate (no "As your AI Finance Controller...", straight to the answer).
- Enforces Tag-Driven Proportionality:
  * `#point_metric`: Exact bold number in sentence 1 + 1-2 bullet points (under 150 words, NO unrequested tables).
  * `#single_order`: Focused 3-way trace table for THAT order only.
  * `#dispute_claim`: Formal Razorpay dispute claim letter using exact calculated overcharge amounts.
  * `#executive_audit`: Structured multi-table executive summary.
"""

import os
import json
import requests
import traceback
import dotenv

dotenv.load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
CANDIDATE_MODELS = ["gemini-3-flash-preview", "gemini-3.1-pro-preview", "gemini-3.1-flash-lite-preview", "gemini-flash-latest"]

SYNTHESIZER_SYSTEM_PROMPT = """You are PrecisionSynthesizerAI — the Presentation Formatter and Question-Answer Alignment AI Agent for AutoReconAI.

YOUR MISSION:
Synthesize a clean, professional, perfectly scoped answer to the merchant's query using the verified facts gathered by ReconAuditorAI.

CRITICAL PRESENTATION RULES:

1. ZERO BOILERPLATE (STRICT):
   - Never use filler intros like "As your AI Finance Controller, I have audited your ledgers..." or "Based on the comprehensive 3-way reconciliation...".
   - Start immediately with the direct answer or table.

2. MATHEMATICAL IMMUTABILITY (CRITICAL RULE):
   - You MUST treat tool outputs from ReconAuditorAI as 100% immutable ground truth.
   - You are STRICTLY FORBIDDEN from performing mental arithmetic, modifying numbers, or hallucinating claim amounts.
   - In dispute claim tickets, the Total Claim Amount MUST strictly equal the calculated overcharge total from `calculate_fee_discrepancies` or `generate_dispute_ticket`.

3. TAG-DRIVEN PROPORTIONAL LAYOUTS:
   - IF TAGGED `#point_metric`:
     * State the exact number in bold in the very first sentence (e.g. "The total recoverable money from Razorpay is **₹85.57** across **9 orders**.").
     * Follow with 1-2 brief bullet points explaining the root cause (e.g. MDR overcharged above contracted 2.00% + 18% GST).
     * DO NOT output full tables or unrelated data dumps. Keep under 150 words.

   - IF TAGGED `#single_order`:
     * Output a clean 3-way trace table for THAT SPECIFIC ORDER ONLY showing: Store Status, Razorpay Status, Billed Amount, Charged Fee, Bank UTR, and Diagnosis.
     * State the recommended operational action (e.g. fulfill manually for dropped webhook, or claim MDR overcharge).

   - IF TAGGED `#dispute_claim`:
     * Format a formal Razorpay Merchant Dispute Claim Ticket dossier addressed to `merchant-support@razorpay.com`.
     * The total claim amount MUST strictly match the exact overcharge sum in the verified tool output. NEVER estimate or hallucinate arbitrary claim amounts.
     * Include a markdown table listing each disputed Order ID, Payment ID, Settlement UTR, Billed Amount, Charged Fee, Contracted Fee, and Overcharge Claim.

   - IF TAGGED `#executive_audit`:
     * Present a clean executive markdown summary table with GMV, Total Fees, Bank Deposited, Match Rate, and the 3 Edge Case breakdown (Dropped Webhooks, Fee Overcharges, Orphan Refunds).

3. MULTI-TURN CONVERSATIONAL ALIGNMENT:
   - When the user asks follow-up questions (e.g. "why is it pending", "is this an improper transaction"), provide a natural financial explanation directly answering their concern without repeating entire unrequested audit reports.
"""

from config_loader import GatewayConfig


class PrecisionSynthesizerAI:
    """Agent 4: Formats and synthesizes the exact, non-bloated, tag-driven response."""

    @staticmethod
    def synthesize_response(user_query: str, router_result: dict, auditor_result: dict, chat_history: list = None) -> dict:
        enriched_query = router_result.get("enriched_query") or user_query
        intent = router_result.get("intent", "COMPREHENSIVE_AUDIT")
        tags = router_result.get("tags", [])
        tool_data = auditor_result.get("collected_tool_data", {})
        auditor_summary = auditor_result.get("auditor_summary", "")
        active_sla = GatewayConfig.get_sla_text()

        if not API_KEY:
            return PrecisionSynthesizerAI._fallback_synthesis(enriched_query, router_result, auditor_result)

        history_context = ""
        if chat_history:
            history_lines = []
            for idx, turn in enumerate(chat_history[-5:], 1):
                u_text = turn.get("user", "")
                a_text = turn.get("assistant", "")
                if len(a_text) > 160:
                    a_text = a_text[:160] + "..."
                history_lines.append(f"[Turn {idx}] User: \"{u_text}\" -> Assistant: \"{a_text}\"")
            history_context = f"RECENT CONVERSATION HISTORY (Last 5 Interactions):\n" + "\n".join(history_lines) + "\n\n"

        context_prompt = (
            f"{SYNTHESIZER_SYSTEM_PROMPT}\n\n"
            f"ACTIVE CONTRACTED SLA TERMS (from config.ini): {active_sla}\n"
            f"{history_context}"
            f"ENRICHED MERCHANT QUERY: \"{enriched_query}\"\n"
            f"INTENT CLASSIFICATION: {intent}\n"
            f"TAGS: {', '.join(tags)}\n\n"
            f"VERIFIED FINANCIAL FACTS & DATA GATHERED BY RECONAUDITORAI:\n"
            f"{json.dumps(tool_data, indent=2)}\n\n"
            f"AUDITOR FINDINGS:\n{auditor_summary}\n\n"
            f"TASK: Synthesize the final direct, zero-boilerplate response following the tag-driven presentation rules strictly."
        )

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": context_prompt}]}
            ]
        }

        for model in CANDIDATE_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
            try:
                resp = requests.post(url, json=payload, timeout=25)
                if resp.status_code == 200:
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return {
                        "final_answer": text,
                        "status": "SYNTHESIZED_ALIGNED"
                    }
                elif resp.status_code == 429:
                    continue
            except Exception:
                continue

        return PrecisionSynthesizerAI._fallback_synthesis(enriched_query, router_result, auditor_result)

    @staticmethod
    def _fallback_synthesis(user_query: str, router_result: dict, auditor_result: dict) -> dict:
        intent = router_result.get("intent", "COMPREHENSIVE_AUDIT")
        tool_data = auditor_result.get("collected_tool_data", {})

        if intent == "POINT_METRIC_QUERY":
            fee_data = tool_data.get("calculate_fee_discrepancies", {})
            total_claim = fee_data.get("total_claimable_overcharge_inr", 0.0)
            orders = [d["order_id"] for d in fee_data.get("discrepancy_details", [])]
            orders_str = ", ".join(orders) if orders else "identified orders"
            ans = (
                f"The total recoverable money from Razorpay is **₹{total_claim:,.2f}** across **{len(orders)} orders**.\n\n"
                f"**Key Findings:**\n"
                f"- Razorpay billed higher MDR rates on orders `{orders_str}`, violating your contracted SLA ({GatewayConfig.get_sla_text()}).\n"
                f"- Dropped webhooks require store fulfillment, and orphan refunds are prior-period customer return adjustments (₹0.00 gateway cash claim)."
            )
            return {"final_answer": ans, "status": "FALLBACK_ALIGNED"}

        return {
            "final_answer": auditor_result.get("auditor_summary", "Audit completed."),
            "status": "FALLBACK_DIRECT"
        }
