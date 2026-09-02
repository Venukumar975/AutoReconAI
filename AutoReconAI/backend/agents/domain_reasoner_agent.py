"""
AutoReconAI - Agent 2: DomainReasonerAI
========================================
Role: Domain Intelligence, Contextual Memory, and Autonomous ReAct Tool Auditor.
- Injected with domain architecture: 3 uploaded file schemas, virtual 3-way matrix join, and 5 commercial edge cases.
- Uses tools_desc.json to dynamically declare all 10 reconciliation tools to Gemini via Native Function Calling.
- Autonomously executes tools, gathers verified ledger records, and resolves multi-turn pronouns from memory.
- Forwards gathered facts and tool outputs directly to Agent 3 (PrecisionSynthesizerAI) for presentation formatting.
"""

import os
import re
import json
import requests
import traceback
import dotenv
dotenv.load_dotenv()

from .tools import ReconToolbox
from config_loader import GatewayConfig, ModelConfig

API_KEY = os.getenv("GEMINI_API_KEY")
CANDIDATE_MODELS = ModelConfig.get_model_fallback_chain()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DESC_PATH = os.path.join(CURRENT_DIR, "tools_desc.json")
TOOLS_REGISTRY_STR = ""
TOOLS_REGISTRY_JSON = {}

if os.path.exists(TOOLS_DESC_PATH):
    try:
        with open(TOOLS_DESC_PATH, "r", encoding="utf-8") as f:
            TOOLS_REGISTRY_STR = f.read()
            TOOLS_REGISTRY_JSON = json.loads(TOOLS_REGISTRY_STR)
    except Exception:
        TOOLS_REGISTRY_STR = ""

DOMAIN_REASONER_SYSTEM_PROMPT = f"""You are DomainReasonerAI (Agent 2) — the Domain Intelligence, Contextual Memory, and Autonomous ReAct Tool Execution Agent for AutoReconAI.

SYSTEM DOMAIN & DATASET ARCHITECTURE:
AutoReconAI performs automated 3-way financial reconciliation across 3 core merchant files:
1. Store Orders Ledger (`store_orders.csv`): `order_id`, `customer_name`, `gross_amount`, `order_status` ('FULFILLED' or 'PENDING'), `created_at`.
2. Razorpay Settlement Payout Ledger (`razorpay_settlement_recon.csv`): `settlement_id`, `settlement_utr`, `payment_id`, `order_id`, `amount`, `fee`, `tax`, `tds`, `net_credit`, `type`, `status`, `created_at`, `settled_at`.
3. Bank Statement Ledger (`bank_statement_union_bank.pdf` / `.xlsx`): `txn_date`, `description` (narration with UTR), `extracted_utr`, `debit`, `credit`, `balance`, `is_gateway_credit`.

5 CORE COMMERCIAL EDGE CASES:
1. Dropped Webhooks: Gateway status 'captured' and settled to bank, but store order status 'PENDING'.
2. MDR Fee Overcharges: Gateway billed MDR fee rate exceeds contracted SLA in config.ini (100% claimable from Razorpay).
3. Orphan Customer Refunds: Settlement contains customer refund deductions; non-reversed MDR+GST is unrecoverable fee leakage.
4. Bank Chargeback Dispute Holds: Customer raised bank dispute; Razorpay debits GMV + ₹590 dispute penalty fee. (Action: PoD within 7 days).
5. Section 194-O Statutory TDS: Advance income tax withheld by gateway on gross sales as per merchant tax profile (Action: Form 26AS credit).

AVAILABLE TOOL REGISTRY (from tools_desc.json):
{TOOLS_REGISTRY_STR}

YOUR MISSION:
1. Carefully analyze the merchant's query, considering conversation history for multi-turn context (e.g. resolving 'this order', 'in a neat table').
2. Call the required tools autonomously to retrieve all facts, calculations, and ledger data from the active session.
3. You can call multiple tools in sequence if the query requires joining or cross-verifying data (e.g. chargeback holds + customer details + overcharge calculations).
4. FOCUS STRICTLY ON FACTUAL DATA RETRIEVAL: Completely ignore visual or presentation directives (such as 'build a chart', 'draw a diagram', 'make a table', 'in a paragraph') — your sole responsibility is executing the appropriate tools to collect raw verified facts. Downstream diagram and layout synthesis is handled exclusively by Agent 3.
"""

# Single Source of Truth: Build TOOL_DECLARATIONS & TOOL_DATA_SOURCES directly from tools_desc.json
function_declarations = []
TOOL_DATA_SOURCES = {}

for tool_meta in TOOLS_REGISTRY_JSON.get("tools", []):
    fn_name = tool_meta.get("function_name")
    fn_desc = tool_meta.get("description", "")
    raw_inputs = tool_meta.get("inputs", {})
    data_sources = tool_meta.get("required_data_sources", [])

    TOOL_DATA_SOURCES[fn_name] = data_sources

    properties = {}
    required_fields = []
    for param_name, param_info in raw_inputs.items():
        p_type = str(param_info.get("type", "string")).upper()
        if "ARRAY" in p_type:
            properties[param_name] = {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": param_info.get("description", "")
            }
        elif "NUMBER" in p_type or "FLOAT" in p_type:
            properties[param_name] = {
                "type": "NUMBER",
                "description": param_info.get("description", "")
            }
        else:
            properties[param_name] = {
                "type": "STRING",
                "description": param_info.get("description", "")
            }
        if param_info.get("required", False) or param_name in ["order_id", "base_amount", "query"]:
            required_fields.append(param_name)

    decl = {
        "name": fn_name,
        "description": fn_desc,
        "parameters": {
            "type": "OBJECT",
            "properties": properties
        }
    }
    if required_fields:
        decl["parameters"]["required"] = required_fields

    function_declarations.append(decl)

TOOL_DECLARATIONS = [{"function_declarations": function_declarations}]


class DomainReasonerAI:
    """Agent 2: Domain Reasoner & Autonomous ReAct Tool Execution Auditor."""

    @staticmethod
    def reason_and_audit(user_query: str, session_data: dict = None, chat_history: list = None) -> dict:
        session_data = session_data or {}
        tools_called_log = []
        collected_tool_results = {}

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

        initial_prompt = (
            f"{DOMAIN_REASONER_SYSTEM_PROMPT}\n\n"
            f"ACTIVE CONTRACTED SLA TERMS (from config.ini): {GatewayConfig.get_sla_text()}\n"
            f"{history_context}\n"
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
                    if resp.status_code != 200:
                        continue

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
                        tool_output = DomainReasonerAI._dispatch_tool(fn_name, fn_args, session_data)
                        loop_results[fn_name] = tool_output
                        loop_tools_log.append({
                            "tool": fn_name,
                            "args": fn_args,
                            "summary": f"Executed {fn_name}()"
                        })

                        # Maintain model turn
                        conversation.append(candidate_content)

                        # Append tool response
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

        # Collect distinct data sources used
        sources_used = []
        for t in tools_called_log:
            fn = t.get("tool")
            for s in TOOL_DATA_SOURCES.get(fn, []):
                if s not in sources_used:
                    sources_used.append(s)

        if not sources_used:
            sources_used = ["Store Orders CSV", "Settlement Payouts CSV", "Bank Statement PDF/XLSX"]

        return {
            "scope": "IN_SCOPE",
            "status": "FACTS_GATHERED",
            "summary": final_summary_text or "Audit facts gathered from live reconciliation ledgers.",
            "collected_tool_data": collected_tool_results,
            "tools_called": tools_called_log,
            "data_sources": sources_used
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
        elif fn_name == "search_statutory_tax_web":
            return ReconToolbox.search_statutory_tax_web(
                query=fn_args.get("query", ""),
                domain=fn_args.get("domain", "incometax")
            )
        return {"error": f"Unknown tool '{fn_name}'"}


# Backward compatibility alias
SentinelRouterAI = DomainReasonerAI
