"""
AutoReconAI - Agent 5: TaxOptimizerAI
======================================
Role: Specialized Executive Settlement Unpacker & GST Tax Strategist Agent
- Analyzes verified settlement unpacking metrics computed deterministically by Python.
- Synthesizes dynamic, professional Indian GST Input Tax Credit (ITC) compliance guidance (Section 16 CGST Act).
- Formulates tailored executive financial FAQs, take-rate evaluations, and risk mitigation strategies in structured JSON.
"""

import json
import os
import re
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(CURRENT_DIR))

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


TAX_OPTIMIZER_SYSTEM_PROMPT = """
You are TaxOptimizerAI, an elite Corporate Finance Controller and Indian GST Tax Compliance Strategist for high-volume enterprise e-commerce merchants using payment gateways like Razorpay.

YOUR MISSION:
You are provided with 100% verified, mathematically exact payment gateway settlement metrics unpacked from the merchant's store orders, settlement ledger, and bank statement.

Analyze the verified metrics and generate:
1. An executive financial assessment summarizing gateway fee efficiency, net cash realization, and GST tax credit yield.
2. Exactly 4 dynamic, highly relevant financial questions and detailed, actionable advisory answers formatted for corporate finance teams:
   - Question 1: Specific guidance on claiming the exact 18% GST Input Tax Credit (ITC) under Section 16 of the CGST Act in monthly GSTR-3B (Table 4A) filings.
   - Question 2: Evaluation of actual gateway take-rate vs contracted SLA benchmark, highlighting any fee leakage.
   - Question 3: Concrete operational advisory regarding dropped webhooks and customer package fulfillment safety.
   - Question 4: Immediate cash recovery steps for verified MDR fee overcharges.

OUTPUT FORMAT:
You MUST respond with strictly valid JSON only (no markdown fences, no extra text):
{
  "executive_summary": "High-level 2-sentence financial health assessment of this settlement batch...",
  "financial_faqs": [
    {
      "question": "1. ...",
      "answer": "..."
    },
    {
      "question": "2. ...",
      "answer": "..."
    },
    {
      "question": "3. ...",
      "answer": "..."
    },
    {
      "question": "4. ...",
      "answer": "..."
    }
  ]
}
"""


class TaxOptimizerAI:

    @staticmethod
    def generate_tax_and_executive_insights(unpacked_facts: dict) -> dict:
        """
        Calls the Gemini model with verified deterministic numbers to produce dynamic
        tax strategies and executive FAQs. Falls back gracefully if API is unavailable.
        """
        api_key = os.getenv("GEMINI_API_KEY", "")
        
        # Format verified facts into prompt context
        facts_summary = f"""
VERIFIED FINANCIAL SETTLEMENT METRICS:
- Active Contracted SLA: {unpacked_facts.get('contracted_sla_text', '2.50% Domestic MDR + 18% GST')}
- Total Gross Sales (GMV): INR {unpacked_facts.get('total_gmv', 0.0):,.2f}
- Net Bank Deposited Payout: INR {unpacked_facts.get('net_bank_payout', 0.0):,.2f} ({unpacked_facts.get('net_payout_pct', 0.0):.2f}% of GMV)
- Gateway MDR Processing Expense: INR {unpacked_facts.get('total_mdr_expense', 0.0):,.2f} ({unpacked_facts.get('mdr_pct', 0.0):.2f}% of GMV)
- Claimable 18% GST Input Tax Credit (ITC): INR {unpacked_facts.get('total_gst_itc', 0.0):,.2f} ({unpacked_facts.get('gst_pct', 0.0):.2f}% of GMV)
- Overall Effective Gateway Take-Rate: {unpacked_facts.get('effective_take_rate', 0.0):.2f}%
- Fee Overcharges Detected: {unpacked_facts.get('overcharge_orders_count', 0)} orders (Total Claimable Cash: INR {unpacked_facts.get('overcharge_claim_inr', 0.0):,.2f})
- Dropped Webhooks: {unpacked_facts.get('dropped_webhooks_count', 0)} orders (Payments captured in gateway, store status PENDING)
- Prior-Period Return Deductions: {unpacked_facts.get('orphan_refunds_count', 0)} orders (Total Netting: INR {unpacked_facts.get('orphan_refunds_amount', 0.0):,.2f})
"""

        from config_loader import ModelConfig

        if GENAI_AVAILABLE and api_key:
            for model_name in ModelConfig.get_model_fallback_chain():
                try:
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            {"role": "user", "parts": [{"text": f"{TAX_OPTIMIZER_SYSTEM_PROMPT}\n\n{facts_summary}"}]}
                        ]
                    )
                    
                    raw_text = response.text.strip()
                    # Clean code blocks if present
                    clean_json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                    if clean_json_match:
                        parsed = json.loads(clean_json_match.group(0))
                        if "financial_faqs" in parsed and isinstance(parsed["financial_faqs"], list):
                            return {
                                "executive_summary": parsed.get("executive_summary", "Settlement batch successfully unpacked and verified."),
                                "financial_faqs": parsed["financial_faqs"],
                                "generated_by": "TaxOptimizerAI (Live Gemini Generative Synthesis)"
                            }
                except Exception as e:
                    continue

        # Deterministic Domain Fallback (Exact math, zero template breakdown)
        total_gmv = unpacked_facts.get('total_gmv', 0.0)
        total_gst = unpacked_facts.get('total_gst_itc', 0.0)
        total_mdr = unpacked_facts.get('total_mdr_expense', 0.0)
        take_rate = unpacked_facts.get('effective_take_rate', 0.0)
        claim_inr = unpacked_facts.get('overcharge_claim_inr', 0.0)
        overcharge_count = unpacked_facts.get('overcharge_orders_count', 0)
        webhook_count = unpacked_facts.get('dropped_webhooks_count', 0)

        return {
            "executive_summary": f"Unpacked INR {total_gmv:,.2f} in gross sales yielding INR {unpacked_facts.get('net_bank_payout', 0.0):,.2f} in net bank deposits. Effective gateway take-rate stands at {take_rate:.2f}%, generating INR {total_gst:,.2f} in verified claimable GST Input Tax Credit.",
            "financial_faqs": [
                {
                    "question": "1. How do I claim the 18% GST Input Tax Credit (ITC) in my tax filings?",
                    "answer": f"Your payment gateway deducted INR {total_gst:,.2f} in 18% GST on processing fees. Under Indian GST law, this is 100% claimable as Input Tax Credit (ITC) under Section 16 of the CGST Act. In your monthly GSTR-3B filing (Table 4A - All other ITC), enter INR {total_gst:,.2f} to reduce your net tax payable to the government."
                },
                {
                    "question": "2. What is the net take-rate deducted by Razorpay across this entire batch?",
                    "answer": f"Across INR {total_gmv:,.2f} in gross sales, total deductions were INR {(total_mdr + total_gst):,.2f} (INR {total_mdr:,.2f} MDR fee + INR {total_gst:,.2f} GST). Your effective overall gateway take-rate was {take_rate:.2f}% vs contracted SLA benchmark."
                },
                {
                    "question": "3. Why are some orders pending in store while captured on the gateway?",
                    "answer": f"There are {webhook_count} dropped webhook orders. The gateway successfully captured funds and transferred them to your bank, but the HTTP webhook acknowledgment was dropped. You can safely release customer packages and mark them FULFILLED."
                },
                {
                    "question": "4. How much cash can I recover immediately via a gateway dispute ticket?",
                    "answer": f"You can recover exactly INR {claim_inr:,.2f} in cash across {overcharge_count} orders where the gateway charged higher interchange rates in breach of your contracted MDR SLA."
                }
            ],
            "generated_by": "TaxOptimizerAI (Deterministic Math Synthesis)"
        }
