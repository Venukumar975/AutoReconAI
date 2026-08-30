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

from config_loader import GatewayConfig, ModelConfig

API_KEY = os.getenv("GEMINI_API_KEY")
CANDIDATE_MODELS = ModelConfig.get_model_fallback_chain()

SYNTHESIZER_SYSTEM_PROMPT = """You are PrecisionSynthesizerAI — the Presentation Formatter and Question-Answer Alignment AI Agent for AutoReconAI.

YOUR MISSION:
Review the merchant's exact question, intent classification, tags, conversation history, and raw verified facts gathered by ReconAuditorAI. Synthesize a clean, professional, perfectly scoped answer that directly answers the question without unrequested bloat or filler intros.

PRESENTATION & LAYOUT GUIDELINES:

1. STANDARD PRE-DEFINED FORMAT TEMPLATES:
   - TEMPLATE 1: Itemized Fee Overcharges Table (`#fee_overcharge_table` or when asked for itemized fee overcharges table):
     * Format a clean Markdown table with EXACT columns:
       | Date | Order ID | Payment ID | Settlement UTR | Billed Amount (INR) | Charged Fee + Tax (INR) | Effective Rate | Contracted Fee + Tax ([Active Contracted SLA Terms, e.g. 2.00% MDR + 18.00% GST = 2.36% SLA]) | Overcharge Amount (INR) |
     * Sort rows chronologically by Date.
     * MUST INCLUDE A TOTAL SUMMARY ROW AS THE LAST ROW OF THE TABLE:
       | **TOTALS** | **[Count] Orders** | - | - | **₹[Total Billed]** | **₹[Total Charged]** | - | **₹[Total Contracted]** | **₹[Total Overcharge]** |
     * Place the bold Total Claimable Overcharge amount immediately below the table.

   - TEMPLATE 2: Formal Razorpay Dispute Claim Ticket (`#dispute_claim` or when asked to draft dispute ticket):
     * Format as a formal, professional email dossier:
       **From:** merchant-disputes@freshmart-store.com  
       **To:** merchant-support@razorpay.com  
       **Subject:** URGENT: MDR Fee Overcharge Dispute Claim - Batch Ref #[Order Count] Orders  
       **Date:** [Current Date / Today]  
       
       Dear Razorpay Support Team,  
       
       We have completed an automated reconciliation audit of our payment settlements against our active contracted SLA terms ([Active Contracted SLA Text]). Our audit identified an SLA breach where [Count] transactions were billed at inflated MDR rates exceeding our contracted threshold.
       
       **Total Claimable Amount:** **₹[Total Overcharge]** across [Count] transactions.  
       
       | Disputed Order ID | Payment ID | Settlement UTR | Billed Amount | Charged MDR | Contracted Fee + Tax ([Active Contracted SLA Terms, e.g. 2.00% MDR + 18.00% GST = 2.36% SLA]) | Claim Amount (INR) |
       [List disputed order rows from tool data]  
       | **TOTALS** | **[Count] Disputed Orders** | - | **INR [Total Billed]** | **INR [Total Charged]** | **INR [Total Contracted]** | **INR [Total Claim Amount]** |
       
       Please review the attached ledger breakdown and process a direct credit adjustment or refund of **₹[Total Overcharge]** to our registered merchant settlement bank account.
       
       **Merchant Account References:**
       * **Merchant Business Name:** FreshMart Online Store
       * **Merchant ID (MID):** MID_FRESHMART_9921
       * **Dispute Contact:** merchant-disputes@freshmart-store.com
       
       Thank you for your prompt assistance in resolving this billing discrepancy.
       
       Sincerely,  
       **Merchant Finance Controller Team**  
       FreshMart Retail Technologies

   - TEMPLATE 3: All Mismatches Grouped Summary (`#mismatch_summary_table` or `#executive_audit` or when asked for mismatch recovery summary):
     * Format a clean summary table grouping all mismatches across the commercial edge cases present in verified tool facts:
       | Mismatch Category | Count | Affected Order IDs | Money Lost? | Recoverable Amount (INR) |
     * Dynamic Financial Inference Rules:
       - **Mismatch Category & Count**: Extract category names and total record counts directly from verified tool facts.
       - **Money Lost?**: Infer financial impact dynamically from facts (e.g., MDR fee overbilling represents actual cash leakage; dropped webhooks represent store status sync delays; orphan refunds represent prior return adjustments).
       - **Recoverable Amount (INR)**: Calculate the numeric claimable amount for cash-recoverable categories directly from verified tool data; for non-leakage operational categories (like webhooks or customer returns), state the exact recoverable monetary figure as **₹0.00**.

2. ZERO BOILERPLATE & NO SPAM:
   - Start immediately with the direct answer. Never use generic intro headers like "As your AI Finance Controller...".
   - Do NOT append repeated sales pitches ("Would you like me to generate a dispute ticket?") unless the user explicitly asked how to take action or file a dispute.

3. HYBRID TABLE & MATHEMATICAL IMMUTABILITY:
   - For standard full report requests (e.g. "give me an itemized fee overcharges table" or full reconciliation summaries), embed the pre-rendered 'default_table_md' string from ReconAuditorAI payload VERBATIM. This guarantees 100% mathematical precision and zero hallucination.
   - For custom conversational requests (e.g. "show me just order ID and overcharge amount in 2 columns" or "show me orders overcharged > 10 rupees"), dynamically construct the custom table from 'discrepancy_details' or 'mismatches' raw records, strictly preserving original values.
   - NEVER recalculate fees or change numbers manually inside the LLM. Use exact pre-calculated values.

4. MULTI-TURN CONVERSATIONAL PRECISION:
   - If the user asks for specific follow-up fields (e.g. "I want customer details too", "what is the customer name?"), output ONLY the requested fields cleanly in 1-2 lines. Never re-dump full reconciliation tables that were already shown in recent turns.
"""


class PrecisionSynthesizerAI:
    """Agent 4: Formats and synthesizes the exact, non-bloated, tag-driven response."""

    @staticmethod
    def synthesize_response(user_query: str, router_result: dict, auditor_result: dict, chat_history: list = None) -> dict:
        enriched_query = router_result.get("enriched_query") or user_query
        intent = router_result.get("intent", "COMPREHENSIVE_AUDIT")

        if not API_KEY:
            return PrecisionSynthesizerAI._fallback_synthesis(user_query, router_result, auditor_result)

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
