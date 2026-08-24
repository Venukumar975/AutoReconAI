"""
AutoReconAI - Agent 3: PrecisionSynthesizerAI
==============================================
Role: Response Formatter, Question-Answer Alignment & Precision Editor Agent.
- Takes User Query + SentinelRouter Intent/Tags + ReconAuditor Raw Tool Facts.
- Enforces strict Question-Answer Alignment and Proportionality:
  * Short targeted questions -> Direct punchy answers with exact figures from live tool data (NO unrequested table dumps).
  * Single order queries -> Laser-focused 3-way trace of that order only.
  * Dispute requests -> Formal Razorpay claim dossier with dynamic order breakdowns.
  * Comprehensive audit requests -> Multi-table executive report.
  * Courtesy messages -> Warm, polite 1-liner.
- 100% Dynamic and dataset-agnostic (extracts all figures from live tool outputs).
"""

import os
import json
import requests
import traceback
import dotenv

dotenv.load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
CANDIDATE_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]

SYNTHESIZER_SYSTEM_PROMPT = """You are PrecisionSynthesizerAI — the Final Synthesis and Question-Answer Alignment AI Agent for AutoReconAI.

YOUR MISSION:
Review the merchant's exact question, the intent classification, and the raw verified facts gathered by ReconAuditorAI. Synthesize a clean, professional, perfectly scoped answer that directly answers the question without unrequested bloat.

CRITICAL SYNTHESIS RULES:

1. QUESTION-ANSWER ALIGNMENT & PROPORTIONALITY (STRICT):
   - If the merchant sent a COURTESY message (e.g. "thank you", "thanks", "hello"):
     * Respond with a warm, polite 1-liner (e.g. "You're very welcome! Let me know if you need to inspect any other transaction or generate dispute claims.").

   - If the merchant asked a focused / point question (e.g., "what is the total recoverable money?", "what is our match rate?", "how much was overcharged?"):
     * DIRECT ANSWER FIRST: Give the exact calculated number from the tool data in bold in the very first sentence.
     * CONCISE BREAKDOWN: Provide 1-2 short bullet points explaining why based on the dynamic findings.
     * DO NOT DUMP UNREQUESTED TABLES: Do NOT print GMV tables, GST totals, or full dropped webhook inventory lists unless explicitly asked for a full audit summary.
     * Keep the response under 150 words.

   - If the merchant asked about a SPECIFIC Order ID (e.g., "what happened to ORD_xxxx?"):
     * Present a clean 3-way trace table for THAT SPECIFIC ORDER ONLY using the tool results.
     * State the exact status, payment ID, fee charged, bank UTR, and recommended action.

   - If the merchant asked for a DISPUTE CLAIM TICKET:
     * Format a clean, official merchant dispute claim letter addressed to `merchant-support@razorpay.com` listing all overcharged order IDs, UTRs, and calculated claim amounts from the tool output.

   - If the merchant asked for a FULL / COMPREHENSIVE AUDIT REPORT:
     * Present the structured executive summary table with Match Rate, GMV, fees, and the 3 mismatch categories calculated dynamically from the tool data.

2. ZERO BOILERPLATE:
   - Do NOT use filler greetings like "As your Senior AI Finance Controller, I have completed a rigorous 3-way reconciliation...".
   - Start immediately with the answer.

3. DOMAIN ACCURACY & DYNAMIC CALCULATIONS:
   - Contracted Merchant SLA Terms: 2.00% Domestic MDR + 18.00% GST (Effective 2.36%).
   - Dynamic Figures: ALWAYS extract exact monetary amounts, order IDs, match rates, and overcharge totals directly from the live tool_data payload. Never invent or assume hardcoded numbers.
   - Financial Categories:
     * Fee Overcharges: Effective rate > 2.36% -> 100% cash-recoverable claim against the gateway.
     * Dropped Webhooks: Store status PENDING vs Gateway CAPTURED -> Requires manual order fulfillment in store (₹0.00 cash claim from PG).
     * Orphan Refunds: Deductions from settlement UTR with negative net credits -> Requires internal ERP ledger adjustment for customer returns.
"""


from config_loader import GatewayConfig

class PrecisionSynthesizerAI:
    """Agent 3: Evaluates facts against user query and synthesizes the exact, non-bloated answer."""

    @staticmethod
    def synthesize_response(user_query: str, router_result: dict, auditor_result: dict) -> dict:
        intent = router_result.get("intent", "COMPREHENSIVE_AUDIT")

        if intent == "COURTESY":
            return {
                "final_answer": "You're very welcome! Let me know if you need to trace any other order, draft another claim, or audit a new ledger batch.",
                "status": "COURTESY_REPLIED"
            }

        if not API_KEY:
            return PrecisionSynthesizerAI._fallback_synthesis(user_query, router_result, auditor_result)

        tags = router_result.get("tags", [])
        tool_data = auditor_result.get("collected_tool_data", {})
        auditor_summary = auditor_result.get("auditor_summary", "")
        active_sla = GatewayConfig.get_sla_text()

        context_prompt = (
            f"{SYNTHESIZER_SYSTEM_PROMPT}\n\n"
            f"ACTIVE CONTRACTED SLA TERMS (from config.ini): {active_sla}\n"
            f"MERCHANT USER QUERY: \"{user_query}\"\n"
            f"INTENT CLASSIFICATION: {intent}\n"
            f"TAGS: {', '.join(tags)}\n\n"
            f"VERIFIED FINANCIAL FACTS & DATA GATHERED BY RECONAUDITORAI:\n"
            f"{json.dumps(tool_data, indent=2)}\n\n"
            f"AUDITOR FINDINGS:\n{auditor_summary}\n\n"
            f"TASK: Synthesize the final, direct, proportional response following the synthesis rules strictly using the facts and active SLA terms above."
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

        return PrecisionSynthesizerAI._fallback_synthesis(user_query, router_result, auditor_result)

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
                f"The total recoverable money from Razorpay is **₹{total_claim:,.2f}**.\n\n"
                f"**Why it is claimable:**\n"
                f"- Razorpay overcharged your Merchant Discount Rate (MDR) on **{len(orders)} orders** (`{orders_str}`), breaching your contracted **2.00% + 18% GST SLA**.\n"
                f"- *(Note: Dropped webhooks require store fulfillment, and orphan refunds require internal ERP adjustment, not cash claims from Razorpay).* \n\n"
                f"👉 *Would you like me to draft the official Razorpay dispute claim ticket for the **₹{total_claim:,.2f}**?*"
            )
            return {"final_answer": ans, "status": "FALLBACK_ALIGNED"}

        return {
            "final_answer": auditor_result.get("auditor_summary", "Audit completed."),
            "status": "FALLBACK_DIRECT"
        }
