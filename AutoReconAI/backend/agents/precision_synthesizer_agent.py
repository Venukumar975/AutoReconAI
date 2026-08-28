"""
AutoReconAI - Agent 4: PrecisionSynthesizerAI
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
Review the merchant's exact question, intent classification, tags, conversation history, and raw verified facts gathered by ReconAuditorAI. Synthesize a clean, professional, perfectly scoped answer that directly answers the question without unrequested bloat or filler intros.

PRESENTATION & LAYOUT GUIDELINES:

1. DYNAMIC PRESENTATION ALIGNMENT:
   - Match the output layout directly to the user's query and assigned tags:
     * `#simple_answer` / `#point_metric`: Answer the core question immediately in 1-2 bold, direct sentences using live verified numbers. Keep under 100 words. Skip unrequested data tables unless explicitly asked.
     * `#loss_recovery_check`: State immediately whether the funds are recoverable or non-recoverable, providing the exact claimable overcharge total from tool data in 1-2 direct sentences.
     * `#single_order` / `#ord_XXXX`: Present a clean 3-way trace table for THAT SPECIFIC ORDER ONLY using verified tool data.
     * `#dispute_claim`: Format a formal merchant dispute claim ticket dossier addressed to `merchant-support@razorpay.com`.
     * `#executive_audit` / `#comprehensive_audit`: Format a structured executive summary report with GMV, match rate, and edge case breakdown tables.
     * `#tax_calculation` / `#gst_details`: State the calculated GST tax in bold and provide the mathematical breakdown.

2. ZERO BOILERPLATE & NO SPAM:
   - Start immediately with the direct answer. Never use generic intro headers like "As your AI Finance Controller...".
   - Do NOT append repeated sales pitches ("Would you like me to generate a dispute ticket?") unless the user explicitly asked how to take action or file a dispute.

3. MATHEMATICAL IMMUTABILITY:
   - Extract exact monetary figures, order IDs, match rates, and overcharges strictly from ReconAuditorAI's verified `tool_data` payload. Never invent or alter numbers.

4. MULTI-TURN CONVERSATIONAL PRECISION:
   - If the user asks for specific follow-up fields (e.g. "I want customer details too", "what is the customer name?"), output ONLY the requested fields cleanly in 1-2 lines. Never re-dump full reconciliation tables that were already shown in recent turns.
"""


from config_loader import GatewayConfig

class PrecisionSynthesizerAI:
    """Agent 4: Evaluates facts against user query and synthesizes the exact, non-bloated answer."""

    @staticmethod
    def synthesize_response(user_query: str, router_result: dict, auditor_result: dict, chat_history: list = None) -> dict:
        intent = router_result.get("intent", "COMPREHENSIVE_AUDIT")

        if not API_KEY:
            return PrecisionSynthesizerAI._fallback_synthesis(user_query, router_result, auditor_result)

        tags = router_result.get("tags", [])
        tool_data = auditor_result.get("collected_tool_data", {})
        auditor_summary = auditor_result.get("auditor_summary", "")
        active_sla = GatewayConfig.get_sla_text()

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
            f"CURRENT MERCHANT USER QUERY: \"{user_query}\"\n"
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
            active_sla = GatewayConfig.get_sla_text()
            ans = (
                f"The total recoverable money from Razorpay is **₹{total_claim:,.2f}**.\n\n"
                f"**Why it is claimable:**\n"
                f"- Razorpay overcharged your Merchant Discount Rate (MDR) on **{len(orders)} orders** (`{orders_str}`), breaching your contracted **{active_sla}**.\n"
                f"- *(Note: Dropped webhooks require store fulfillment, and orphan refunds require internal ERP adjustment, not cash claims from Razorpay).* \n\n"
                f"👉 *Would you like me to draft the official Razorpay dispute claim ticket for the **₹{total_claim:,.2f}**?*"
            )
            return {"final_answer": ans, "status": "FALLBACK_ALIGNED"}

        return {
            "final_answer": auditor_result.get("auditor_summary", "Audit completed."),
            "status": "FALLBACK_DIRECT"
        }
