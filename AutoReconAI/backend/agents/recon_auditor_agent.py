"""
AutoReconAI - Agent 3: ReconAuditorAI
======================================
Role: Fact Gatherer & Tool Calling Auditor Agent.
- Receives the clean, enriched query and structured tags from DomainReasonerAI (Agent 2).
- Autonomously executes dynamic reconciliation tools via Gemini Function Calling.
- Gathers raw verified facts, numbers, fee variances, and ledger records.
- Forwards gathered data and tool outputs to PrecisionSynthesizerAI for tailored synthesis.
"""

import os
import json
import requests
import traceback
import dotenv
dotenv.load_dotenv()
from .tools import ReconToolbox
from config_loader import GatewayConfig, ModelConfig

API_KEY = os.getenv("GEMINI_API_KEY")
CANDIDATE_MODELS = ModelConfig.get_model_fallback_chain()

AUDITOR_SYSTEM_PROMPT = """You are ReconAuditorAI — the Fact Gathering and Tool-Calling Execution AI Agent for AutoReconAI.

YOUR MISSION:
Analyze the merchant's query and intent tags. Call the necessary tools to retrieve all required facts, calculations, and ledger data from the live session:
- get_reconciliation_overview: For match rates, GMV, total fees, and high-level stats.
- calculate_fee_discrepancies: For exact MDR fee overcharge calculations (2.00% SLA breach).
- calculate_refund_fee_leakage: For calculating non-reversed MDR fees + 18% GST overhead losses on customer refunds.
- audit_chargeback_holds: For customer bank dispute holds, chargeback deductions, and Proof of Delivery requirements.
- audit_tax_and_tds_deductions: For Section 194-O TDS withholding and claimable GST Input Tax Credit (ITC).
- inspect_order_lifecycle: For tracing a specific Order ID across 3 ledgers.
- list_mismatches: For anomaly lists (dropped webhooks, orphan refunds, fee overcharges).
- query_gateway_payments_db: For inspecting Razorpay gateway core payments database.
- generate_dispute_ticket: For compiling dispute claim ticket payloads.

MULTI-TOOL EXECUTION DIRECTIVE:
You have full capability to execute MULTIPLE TOOLS in sequence. If a user's request asks for composite financial insights (e.g. fee overcharges + dispute claim, or chargeback holds + refund fee leakage, or order trace + raw gateway DB lookup, or statutory tax + reconciliation overview), DO NOT stop after 1 tool. Call all relevant tools sequentially so the synthesizer has complete facts.
"""

TOOL_DECLARATIONS = [
    {
        "functionDeclarations": [
            {
                "name": "get_reconciliation_overview",
                "description": "Get high-level financial reconciliation health metrics across all 3 ledgers: Total Settlement Transactions, GMV, Total Fees, Total GST, Total Bank Deposited, Match Rate, and Mismatch breakdown.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "calculate_refund_fee_leakage",
                "description": "Calculates dynamic non-reversed MDR fee and 18% GST cash losses on customer refunds. Call this when analyzing customer refunds, orphan refunds, non-recoverable losses, or refund fee overheads.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "list_mismatches",
                "description": "List all mismatched orders with their anomaly details, filtered by category ('all', 'fee_overcharge', 'dropped_webhook', 'orphan_refund', 'missing_bank_credit').",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "category": {
                            "type": "STRING",
                            "description": "Filter by anomaly category: 'all', 'fee_overcharge', 'dropped_webhook', 'orphan_refund', or 'missing_bank_credit'."
                        }
                    },
                    "required": ["category"]
                }
            },
            {
                "name": "inspect_order_lifecycle",
                "description": "Perform deep 3-way trace of a specific Order ID across Store Order Ledger, Razorpay Settlement Ledger, and Bank Statement Ledger.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "order_id": {
                            "type": "STRING",
                            "description": "The exact Order ID to inspect (e.g., 'ORD_1002', 'ORD_1004', 'ORD_PRIOR_901')."
                        }
                    },
                    "required": ["order_id"]
                }
            },
            {
                "name": "calculate_fee_discrepancies",
                "description": "Perform mathematical fee audit comparing actual billed MDR vs active contracted SLA terms for all overcharged transactions, returning exact claimable overcharge amounts.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "query_gateway_payments_db",
                "description": "Read-only inspection of Razorpay's authentic Payment Gateway database ('payments' table). Note: Client-side store tables like 'orders', 'cart', 'products' are merchant private data and NOT accessible in gateway DB.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "filter_key": {
                            "type": "STRING",
                            "description": "Optional column name to filter on ('order_id', 'payment_id', 'status', 'settlement_utr')."
                        },
                        "filter_value": {
                            "type": "STRING",
                            "description": "Optional value to match."
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "generate_dispute_ticket",
                "description": "Generate an official, formatted Razorpay Merchant Dispute Claim Ticket dossier for specific order IDs.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "order_ids": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "description": "List of Order IDs to include in the dispute claim ticket."
                        },
                        "reason": {
                            "type": "STRING",
                            "description": "The primary dispute reason (e.g., 'Gateway MDR Rate SLA Violation')."
                        }
                    },
                    "required": ["order_ids"]
                }
            },
            {
                "name": "calculate_tax_breakdown",
                "description": "Calculate exact GST tax amount and total deduction on a base MDR processing fee or transaction amount.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "base_amount": {
                            "type": "NUMBER",
                            "description": "The base fee or transaction amount in INR (e.g., 15000.00)."
                        },
                        "tax_rate_pct": {
                            "type": "NUMBER",
                            "description": "The GST tax rate percentage (default 18.0 for standard Indian GST)."
                        }
                    },
                    "required": ["base_amount"]
                }
            },
            {
                "name": "audit_chargeback_holds",
                "description": "Audits all customer bank chargebacks, dispute holds, and non-refundable dispute handling fees with Proof of Delivery defense requirements.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "audit_tax_and_tds_deductions",
                "description": "Audits Section 194-O Statutory TDS deductions and claimable GST Input Tax Credit (ITC) on gateway MDR fees.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                    "required": []
                }
            }
        ]
    }
]


class ReconAuditorAI:
    """Agent 3: Executes dynamic tool calling using user query & tags, gathering raw facts."""

    @staticmethod
    def audit_and_gather_facts(user_query: str, router_result: dict, session_data: dict) -> dict:
        tools_called_log = []
        collected_tool_results = {}

        intent = router_result.get("intent", "COMPREHENSIVE_AUDIT")
        tags_str = ", ".join(router_result.get("tags", []))
        extracted_oid = router_result.get("extracted_entities", {}).get("order_id")

        initial_prompt = (
            f"{AUDITOR_SYSTEM_PROMPT}\n\n"
            f"ACTIVE CONTRACTED SLA TERMS (from config.ini): {GatewayConfig.get_sla_text()}\n"
            f"[DomainReasonerAI Analysis]:\n"
            f"- Intent: {intent}\n"
            f"- Tags: {tags_str}\n"
            f"- Extracted Entities: {json.dumps(router_result.get('extracted_entities', {}))}\n\n"
            f"MERCHANT USER QUERY: \"{user_query}\""
        )

        success = False
        final_summary_text = ""

        for model in CANDIDATE_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
            conversation = [
                {"role": "user", "parts": [{"text": initial_prompt}]}
            ]
            loop_tools_log = []
            loop_results = {}

            for _ in range(4):
                payload = {
                    "contents": conversation,
                    "tools": TOOL_DECLARATIONS
                }

                try:
                    resp = requests.post(url, json=payload, timeout=30)
                    if resp.status_code == 429:
                        break
                    if resp.status_code != 200:
                        break

                    resp_json = resp.json()
                    candidates = resp_json.get("candidates", [])
                    if not candidates:
                        break

                    candidate_content = candidates[0].get("content", {})
                    parts = candidate_content.get("parts", [])

                    function_call_part = next((p for p in parts if "functionCall" in p), None)

                    if function_call_part:
                        fn_name = function_call_part["functionCall"]["name"]
                        fn_args = function_call_part["functionCall"].get("args", {})

                        # Dispatch Tool
                        tool_output = ReconAuditorAI._dispatch_tool(fn_name, fn_args, session_data)
                        loop_results[fn_name] = tool_output
                        loop_tools_log.append({
                            "tool": fn_name,
                            "args": fn_args,
                            "summary": f"Executed {fn_name}()"
                        })

                        # Maintain model turn
                        conversation.append(candidate_content)

                        # Append tool result
                        conversation.append({
                            "role": "user",
                            "parts": [
                                {
                                    "functionResponse": {
                                        "name": fn_name,
                                        "response": tool_output
                                    }
                                }
                            ]
                        })
                    else:
                        final_text = parts[0].get("text", "") if parts else ""
                        success = True
                        final_summary_text = final_text
                        collected_tool_results = loop_results
                        tools_called_log = loop_tools_log
                        break

                except Exception:
                    break

            if success:
                break

        return {
            "auditor_summary": final_summary_text or "Audit facts gathered from live reconciliation ledgers.",
            "collected_tool_data": collected_tool_results,
            "tools_called": tools_called_log
        }

    @staticmethod
    def _dispatch_tool(fn_name: str, fn_args: dict, session_data: dict):
        if fn_name == "get_reconciliation_overview":
            return ReconToolbox.get_reconciliation_overview(session_data)
        elif fn_name == "list_mismatches":
            return ReconToolbox.list_mismatches(session_data, category=fn_args.get("category", "all"))
        elif fn_name == "inspect_order_lifecycle":
            return ReconToolbox.inspect_order_lifecycle(session_data, order_id=fn_args.get("order_id", ""))
        elif fn_name == "calculate_fee_discrepancies":
            return ReconToolbox.calculate_fee_discrepancies(session_data)
        elif fn_name == "calculate_refund_fee_leakage":
            return ReconToolbox.calculate_refund_fee_leakage(session_data)
        elif fn_name == "audit_chargeback_holds":
            return ReconToolbox.audit_chargeback_holds(session_data)
        elif fn_name == "audit_tax_and_tds_deductions":
            return ReconToolbox.audit_tax_and_tds_deductions(session_data)
        elif fn_name == "query_gateway_payments_db":
            return ReconToolbox.query_gateway_payments_db(
                filter_key=fn_args.get("filter_key"),
                filter_value=fn_args.get("filter_value")
            )
        elif fn_name == "generate_dispute_ticket":
            return ReconToolbox.generate_dispute_ticket(
                session_data=session_data,
                order_ids=fn_args.get("order_ids", []),
                reason=fn_args.get("reason", "Gateway MDR SLA Overcharge")
            )
        elif fn_name == "calculate_tax_breakdown":
            return ReconToolbox.calculate_tax_breakdown(
                base_amount=fn_args.get("base_amount", 0.0),
                tax_rate_pct=fn_args.get("tax_rate_pct", 18.0)
            )
        return {"error": f"Unknown tool '{fn_name}'"}

        # 3. Customer Bank Chargeback Holds
        if intent == "CHARGEBACK_AUDIT" or any(t in tags for t in ["#chargeback_hold", "#bank_dispute"]) or any(k in q_lower for k in ["chargeback", "dispute hold", "escrow", "cash-at-risk", "cash risk"]):
            collected["audit_chargeback_holds"] = ReconToolbox.audit_chargeback_holds(session_data)
            tools_log.append({"tool": "audit_chargeback_holds", "args": {}, "summary": "Audited customer chargebacks & dispute holds"})

        # 4. Refund Fee Leakage
        if any(k in q_lower for k in ["refund fee", "fee leakage", "leakage", "unreversed fee", "cash-at-risk", "cash risk"]):
            collected["calculate_refund_fee_leakage"] = ReconToolbox.calculate_refund_fee_leakage(session_data)
            tools_log.append({"tool": "calculate_refund_fee_leakage", "args": {}, "summary": "Calculated refund fee leakage"})

        # 5. Section 194-O TDS & GST ITC
        if intent == "TAX_TDS_ITC_AUDIT" or any(t in tags for t in ["#section_194o_tds", "#gst_itc", "#tax_reconciliation"]) or any(k in q_lower for k in ["tds", "itc", "194-o", "gstr-3b", "tax audit"]):
            collected["audit_tax_and_tds_deductions"] = ReconToolbox.audit_tax_and_tds_deductions(session_data)
            tools_log.append({"tool": "audit_tax_and_tds_deductions", "args": {}, "summary": "Audited Section 194-O TDS & GST ITC"})

        # 6. Single Order Lifecycle Trace
        if extracted_oid:
            collected["inspect_order_lifecycle"] = ReconToolbox.inspect_order_lifecycle(session_data, order_id=extracted_oid)
            tools_log.append({"tool": "inspect_order_lifecycle", "args": {"order_id": extracted_oid}, "summary": f"Traced order {extracted_oid}"})

        # 7. Gateway Payments Database Query
        if any(k in q_lower for k in ["gateway db", "payments table", "database", "gateway database", "raw gateway"]):
            filter_v = extracted_oid if extracted_oid else None
            filter_k = "order_id" if filter_v else None
            collected["query_gateway_payments_db"] = ReconToolbox.query_gateway_payments_db(filter_key=filter_k, filter_value=filter_v)
            tools_log.append({"tool": "query_gateway_payments_db", "args": {"filter_key": filter_k, "filter_value": filter_v}, "summary": "Queried gateway payments database"})

        # 8. Mismatches List
        if any(k in q_lower for k in ["dropped webhook", "pending in store", "list mismatches", "anomaly list"]):
            collected["list_mismatches"] = ReconToolbox.list_mismatches(session_data, category="dropped_webhook" if "webhook" in q_lower else "all")
            tools_log.append({"tool": "list_mismatches", "args": {}, "summary": "Fetched category mismatch list"})

        # 9. Macro Reconciliation Overview (Default fallback if nothing else collected)
        if not collected or intent == "COMPREHENSIVE_AUDIT" or any(k in q_lower for k in ["match rate", "overview", "macro", "overall 3-way", "5 edge cases", "all mismatches", "summary table"]):
            collected["get_reconciliation_overview"] = ReconToolbox.get_reconciliation_overview(session_data)
            tools_log.append({"tool": "get_reconciliation_overview", "args": {}, "summary": "Fetched high-level ledger stats"})

        return {
            "auditor_summary": "Retrieved financial ledger facts.",
            "collected_tool_data": collected,
            "tools_called": tools_log
        }
