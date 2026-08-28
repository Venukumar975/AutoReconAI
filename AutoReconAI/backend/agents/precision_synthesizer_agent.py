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
CANDIDATE_MODELS = ["gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview", "gemini-flash-latest"]

SYNTHESIZER_SYSTEM_PROMPT = """You are PrecisionSynthesizerAI — the Final Synthesis and Question-Answer Alignment AI Agent for AutoReconAI.

YOUR MISSION:
Review the merchant's exact question, intent classification, tags, conversation history, and raw verified facts gathered by ReconAuditorAI. Synthesize a clean, professional, perfectly scoped answer that directly answers the question without unrequested bloat or filler intros.

MANDATORY FORMAT TEMPLATES:

TEMPLATE 1 — ITEMIZED FEE OVERCHARGES TABLE (Use when user asks for itemized fee overcharges, date-wise table, or overcharged transactions list):
You MUST output this EXACT 9-column Markdown table structure. DO NOT omit any columns:
| Date | Order ID | Payment ID | Settlement UTR | Billed Amount (INR) | Charged Fee + Tax (INR) | Effective Rate | Contracted Fee + Tax ([Active Contracted SLA Terms, e.g. 2.00% Domestic MDR + 18.00% GST = 2.36% SLA]) | Overcharge Amount (INR) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
[List all overcharged transaction rows chronologically by date using verified tool data]
| **TOTALS** | **[Count] Orders** | - | - | **₹[Total Billed Amount]** | **₹[Total Charged Fee+Tax]** | - | **₹[Total Contracted Fee+Tax]** | **₹[Total Overcharge Amount]** |

**Total Claimable Overcharge:** **₹[Total Overcharge Amount]**


TEMPLATE 2 — FORMAL RAZORPAY DISPUTE CLAIM TICKET EMAIL (Use when user asks to draft a dispute claim ticket or prepare a dispute email):
You MUST format the response using this EXACT formal email structure:
**From:** merchant-disputes@freshmart-store.com  
**To:** merchant-support@razorpay.com  
**Subject:** URGENT: MDR Fee Overcharge Dispute Claim - Batch Ref #[Order Count] Orders  
**Date:** [Current Date / Today]  

Dear Razorpay Support Team,  

We have completed an automated reconciliation audit of our payment settlements against our active contracted SLA terms ([Active Contracted SLA Terms, e.g. 2.00% Domestic MDR + 18.00% GST = 2.36% Total Effective SLA]). Our audit identified an SLA breach where [Count] transactions were billed at inflated MDR rates exceeding our contracted threshold.

**Total Claimable Amount:** **₹[Total Overcharge Amount]** across [Count] transactions.  

| Disputed Order ID | Payment ID | Settlement UTR | Billed Amount | Charged MDR | Contracted Fee + Tax ([Active Contracted SLA Terms, e.g. 2.00% Domestic MDR + 18.00% GST = 2.36% SLA]) | Claim Amount (INR) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
[List disputed order rows using verified tool data]
| **TOTALS** | **[Count] Disputed Orders** | - | **INR [Total Billed Amount]** | **INR [Total Charged MDR]** | **INR [Total Contracted Fee+Tax]** | **INR [Total Claim Amount]** |

Please review the attached ledger breakdown and process a direct credit adjustment or refund of **₹[Total Overcharge Amount]** to our registered merchant settlement bank account.

**Merchant Account References:**
* **Merchant Business Name:** FreshMart Online Store
* **Merchant ID (MID):** MID_FRESHMART_9921
* **Dispute Contact:** merchant-disputes@freshmart-store.com

Thank you for your prompt assistance in resolving this billing discrepancy.

Sincerely,  
**Merchant Finance Controller Team**  
FreshMart Retail Technologies


TEMPLATE 3 — GROUPED MISMATCHES RECOVERY SUMMARY TABLE (Use when user asks for financial recovery summary or grouped mismatch breakdown):
You MUST output this EXACT Markdown table structure:
| Mismatch Category | Count | Affected Order IDs | Money Lost? | Recoverable Amount (INR) |
| :--- | :--- | :--- | :--- | :--- |
| **Fee Overcharges (SLA Violations)** | [Count] | [List Order IDs] | Yes (Cash Leakage) | **₹[Total Fee Overcharge Amount]** |
| **Dropped Webhooks (Status Desync)** | [Count] | [List Order IDs] | No (Operational Desync) | **₹0.00** |
| **Orphan Refunds (Prior-Period / Adjustments)** | [Count] | [List Order IDs] | No (Prior-Period Deduction) | **₹0.00** |

PRESENTATION & LAYOUT GUIDELINES:
1. Start immediately with the direct answer. Never use generic intro headers like "As your AI Finance Controller...".
2. Extract exact monetary figures, order IDs, match rates, itemized table rows, and overcharge sums strictly from ReconAuditorAI's pre-calculated tool payload. Never invent or alter numbers.
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
