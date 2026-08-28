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
from .tools import ReconToolbox
from config_loader import GatewayConfig

dotenv.load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
CANDIDATE_MODELS = ["gemini-3-flash-preview", "gemini-3.1-pro-preview", "gemini-3.1-flash-lite-preview", "gemini-flash-latest"]

AUDITOR_SYSTEM_PROMPT = """You are ReconAuditorAI — the Fact Gathering and Tool-Calling Execution AI Agent for AutoReconAI.

YOUR MISSION:
Analyze the merchant's enriched query and DomainReasonerAI's intent tags. Call the necessary tools to retrieve all required facts, calculations, and ledger data from the live session:
- get_reconciliation_overview: For match rates, GMV, total fees, and high-level stats.
- calculate_fee_discrepancies: For exact MDR fee overcharge calculations (2.00% SLA breach).
- inspect_order_lifecycle: For tracing a specific Order ID across 3 ledgers.
- list_mismatches: For anomaly lists (dropped webhooks, orphan refunds, fee overcharges).
- query_gateway_payments_db: For inspecting Razorpay gateway core payments database.
- generate_dispute_ticket: For compiling dispute claim ticket payloads.

CRITICAL EXECUTION RULES:
- If intent is "DISPUTE_CLAIM" or tags contain "#dispute_claim", you MUST call `calculate_fee_discrepancies` or `generate_dispute_ticket`.
- If intent is "SINGLE_ORDER_TRACE" or tags contain a specific order ID, you MUST call `inspect_order_lifecycle`.
- If intent is "POINT_METRIC_QUERY", call `calculate_fee_discrepancies` (for overcharge/claim questions) or `get_reconciliation_overview` (for match rate/GMV questions).

After executing the tools, summarize the verified numerical facts directly.
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
            }
        ]
    }
]


class ReconAuditorAI:
    """Agent 3: Executes dynamic tool calling using enriched query & tags, gathering raw facts."""

    @staticmethod
    def audit_and_gather_facts(user_query: str, router_result: dict, session_data: dict) -> dict:
        tools_called_log = []
        collected_tool_results = {}

        enriched_query = router_result.get("enriched_query") or user_query
        intent = router_result.get("intent", "COMPREHENSIVE_AUDIT")
        tags_str = ", ".join(router_result.get("tags", []))
        extracted_oid = router_result.get("extracted_entities", {}).get("order_id")

        if not API_KEY:
            return ReconAuditorAI._fallback_auditor(enriched_query, router_result, session_data, tools_called_log)

        initial_prompt = (
            f"{AUDITOR_SYSTEM_PROMPT}\n\n"
            f"ACTIVE CONTRACTED SLA TERMS (from config.ini): {GatewayConfig.get_sla_text()}\n"
            f"[DomainReasonerAI Analysis]:\n"
            f"- Intent: {intent}\n"
            f"- Tags: {tags_str}\n"
            f"- Extracted Entities: {json.dumps(router_result.get('extracted_entities', {}))}\n"
            f"- Enriched Query: {enriched_query}\n\n"
            f"ORIGINAL QUERY: {user_query}"
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

                        # --- GUARANTEED TOOL CALL ENFORCER ---
                        intent = router_result.get("intent", "")
                        tags = router_result.get("tags", [])

                        if intent == "DISPUTE_CLAIM" or any(t in tags for t in ["#dispute_claim", "#dispute_ticket"]):
                            if "generate_dispute_ticket" not in loop_results:
                                ticket_output = ReconToolbox.generate_dispute_ticket(session_data)
                                loop_results["generate_dispute_ticket"] = ticket_output
                                loop_tools_log.append({"tool": "generate_dispute_ticket", "args": {}, "summary": "Compiled dispute claim ticket"})

                        if any(t in tags for t in ["#fee_overcharge", "#fee_overcharge_table", "#recoverable_amount", "#summary_row"]) or intent in ["POINT_METRIC_QUERY", "COMPREHENSIVE_AUDIT"]:
                            if "calculate_fee_discrepancies" not in loop_results:
                                fee_output = ReconToolbox.calculate_fee_discrepancies(session_data)
                                loop_results["calculate_fee_discrepancies"] = fee_output
                                loop_tools_log.append({"tool": "calculate_fee_discrepancies", "args": {}, "summary": "Executed calculate_fee_discrepancies()"})

                        return {
                            "auditor_summary": final_text,
                            "collected_tool_data": loop_results,
                            "tools_called": loop_tools_log
                        }

                except Exception:
                    break

            if success:
                break

        if not success or not collected_tool_results:
            return ReconAuditorAI._fallback_auditor(enriched_query, router_result, session_data, tools_called_log)

        # Safety Check: Guarantee critical tool outputs based on Intent
        if intent == "DISPUTE_CLAIM" and "calculate_fee_discrepancies" not in collected_tool_results:
            fee_data = ReconToolbox.calculate_fee_discrepancies(session_data)
            collected_tool_results["calculate_fee_discrepancies"] = fee_data
            tools_called_log.append({"tool": "calculate_fee_discrepancies", "args": {}, "summary": "Calculated MDR fee discrepancies (Guaranteed)"})

        if intent == "SINGLE_ORDER_TRACE" and extracted_oid and "inspect_order_lifecycle" not in collected_tool_results:
            order_data = ReconToolbox.inspect_order_lifecycle(session_data, order_id=extracted_oid)
            collected_tool_results["inspect_order_lifecycle"] = order_data
            tools_called_log.append({"tool": "inspect_order_lifecycle", "args": {"order_id": extracted_oid}, "summary": f"Traced order {extracted_oid} (Guaranteed)"})

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

    @staticmethod
    def _fallback_auditor(query: str, router_result: dict, session_data: dict, tools_log: list = None):
        intent = router_result.get("intent", "COMPREHENSIVE_AUDIT")
        extracted_oid = router_result.get("extracted_entities", {}).get("order_id")
        tools_log = tools_log or []
        collected = {}

        if intent in ["POINT_METRIC_QUERY", "DISPUTE_CLAIM"]:
            fee_data = ReconToolbox.calculate_fee_discrepancies(session_data)
            collected["calculate_fee_discrepancies"] = fee_data
            tools_log.append({"tool": "calculate_fee_discrepancies", "args": {}, "summary": "Calculated MDR overcharges"})
        elif intent == "SINGLE_ORDER_TRACE" and extracted_oid:
            order_data = ReconToolbox.inspect_order_lifecycle(session_data, order_id=extracted_oid)
            collected["inspect_order_lifecycle"] = order_data
            tools_log.append({"tool": "inspect_order_lifecycle", "args": {"order_id": extracted_oid}, "summary": f"Traced order {extracted_oid}"})
        else:
            overview = ReconToolbox.get_reconciliation_overview(session_data)
            collected["get_reconciliation_overview"] = overview
            tools_log.append({"tool": "get_reconciliation_overview", "args": {}, "summary": "Fetched high-level ledger stats"})

        return {
            "auditor_summary": "Retrieved financial ledger facts.",
            "collected_tool_data": collected,
            "tools_called": tools_log
        }
