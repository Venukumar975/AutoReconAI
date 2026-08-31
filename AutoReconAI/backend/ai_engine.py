"""
AutoReconAI - Financial AI Controller Pipeline Orchestrator
============================================================
Coordinates the 3-Agent Multi-Agent Architecture with Dependency Gating:
1. SentinelFirewallAI    -> Agent 1: Hybrid Deterministic & Semantic Security Firewall, Scope Guardrail & Courtesy Bypass.
2. DomainReasonerAI      -> Agent 2: Domain Context Reasoner, Memory Manager & Autonomous ReAct Tool Execution Auditor.
3. PrecisionSynthesizerAI -> Agent 3: Pure Presentation Formatter delivering direct, zero-boilerplate, mathematically immutable answers.
"""

import sys
import os
from collections import deque

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

from agents.ingestion_auditor_agent import SentinelFirewallAI
from agents.sentinel_router_agent import DomainReasonerAI
from agents.precision_synthesizer_agent import PrecisionSynthesizerAI
from agents.tools import ReconToolbox

# In-Memory Sliding Context Window (Stores last 5 interactions in RAM with zero DB overhead)
SESSION_CHAT_MEMORY = deque(maxlen=5)


class AIFinanceEngine:

    @staticmethod
    def execute_pipeline(user_query: str, session_data: dict) -> dict:
        """
        Executes the 3-Stage Conversational AI Pipeline with dynamic dependency evaluation:
        Stage 1: SentinelFirewallAI (Security, Scope & Ingestion Gatekeeper)
        Stage 2: DomainReasonerAI (Domain Reasoning, Autonomous ReAct Tool Calling & Verified Fact Gathering)
        Stage 3: PrecisionSynthesizerAI (Mathematical Immutability & Tag-Aligned Presentation Formatting)
        """
        history_snapshot = list(SESSION_CHAT_MEMORY)

        # --- STAGE 1: SentinelFirewallAI (Agent 1: Security Firewall & Ingestion Gatekeeper) ---
        firewall_check = SentinelFirewallAI.inspect_query_security_and_scope(user_query, session_data)
        if not firewall_check.get("ready"):
            return {
                "success": True,
                "pipeline": {
                    "agent_1": {
                        "name": "SentinelFirewallAI",
                        "status": firewall_check.get("status", "BLOCKED"),
                        "scope": firewall_check.get("scope", "OUT_OF_SCOPE")
                    },
                    "agent_2": {
                        "name": "DomainReasonerAI",
                        "status": "SKIPPED"
                    },
                    "agent_3": {
                        "name": "PrecisionSynthesizerAI",
                        "status": "SKIPPED"
                    }
                },
                "answer": firewall_check.get("message", "Request blocked by Security Firewall.")
            }

        # --- STAGE 2: DomainReasonerAI (Agent 2: Autonomous ReAct Tool Execution & Fact Gathering) ---
        reasoner_result = DomainReasonerAI.reason_and_audit(user_query, session_data, history_snapshot)

        # --- STAGE 3: PrecisionSynthesizerAI (Agent 3: Tag-Driven Presentation Formatting) ---
        synthesizer_result = PrecisionSynthesizerAI.synthesize_response(user_query, reasoner_result, history_snapshot)
        final_answer = synthesizer_result.get("final_answer", "")

        # Save turn into in-memory sliding cache
        SESSION_CHAT_MEMORY.append({
            "user": user_query,
            "assistant": final_answer,
            "tools_called": reasoner_result.get("tools_called", [])
        })

        return {
            "success": True,
            "pipeline": {
                "agent_1": {
                    "name": "SentinelFirewallAI",
                    "status": "SECURITY_CLEARED",
                    "scope": "IN_SCOPE"
                },
                "agent_2": {
                    "name": "DomainReasonerAI",
                    "status": "FACTS_GATHERED",
                    "tools_called": reasoner_result.get("tools_called", []),
                    "summary": reasoner_result.get("summary", "")
                },
                "agent_3": {
                    "name": "PrecisionSynthesizerAI",
                    "status": "TAG_ALIGNED_SYNTHESIS"
                }
            },
            "answer": final_answer
        }

    @staticmethod
    def reset_chat_memory():
        """Clears in-memory sliding context window on session reset."""
        SESSION_CHAT_MEMORY.clear()
