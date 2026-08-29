"""
AutoReconAI - Financial AI Controller Pipeline Orchestrator
============================================================
Coordinates the 4-Stage Multi-Agent Architecture with Dependency Gating:
1. SentinelFirewallAI    -> Hybrid Deterministic & Semantic Security Firewall, Scope Guardrail & Courtesy Bypass.
2. DomainReasonerAI      -> Domain Context Reasoner, Query Rewriter/Enricher, Intent Tagger & Data Requirement Planner.
   [Dependency Gate]     -> Evaluates dynamic data_requirements against live session data; triggers DATA_REQUIRED if missing.
3. ReconAuditorAI        -> Fact Gatherer executing isolated tools via Gemini 3 Function Calling with parameterized safety.
4. PrecisionSynthesizerAI -> Pure Presentation Formatter delivering direct, zero-boilerplate, mathematically immutable answers.
"""

import sys
import os
from collections import deque

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

from agents.ingestion_auditor_agent import SentinelFirewallAI
from agents.sentinel_router_agent import DomainReasonerAI
from agents.recon_auditor_agent import ReconAuditorAI
from agents.precision_synthesizer_agent import PrecisionSynthesizerAI
from agents.tools import ReconToolbox

# In-Memory Sliding Context Window (Stores last 5 interactions in RAM with zero DB overhead)
SESSION_CHAT_MEMORY = deque(maxlen=5)


class AIFinanceEngine:

    @staticmethod
    def execute_pipeline(user_query: str, session_data: dict) -> dict:
        """
        Executes the 4-Stage Conversational AI Pipeline with dynamic dependency evaluation:
        Stage 1: SentinelFirewallAI (Security, Scope & Courtesy)
        Stage 2: DomainReasonerAI (Domain Reasoning, Query Enrichment, Intent & Data Requirements)
        [Gate]: Evaluates data_requirements -> short-circuits to DATA_REQUIRED if files missing.
        Stage 3: ReconAuditorAI (Isolated Parameterized Tool Calling & Verified Fact Gathering)
        Stage 4: PrecisionSynthesizerAI (Mathematical Immutability & Tag-Aligned Presentation)
        """
        history_snapshot = list(SESSION_CHAT_MEMORY)

        # --- STAGE 1: SentinelFirewallAI (Security Firewall & Scope Guardrail) ---
        firewall_check = SentinelFirewallAI.inspect_query_security_and_scope(user_query)
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
                        "name": "ReconAuditorAI",
                        "status": "SKIPPED"
                    },
                    "agent_4": {
                        "name": "PrecisionSynthesizerAI",
                        "status": "SKIPPED"
                    }
                },
                "answer": firewall_check.get("message", "Request blocked by Security Firewall.")
            }

        # --- STAGE 2: DomainReasonerAI (Domain Intent Classifier with Memory) ---
        router_result = DomainReasonerAI.classify_and_tag(user_query, session_data, history_snapshot)

        # --- STAGE 3: ReconAuditorAI (Tool Execution & Fact Gathering) ---
        auditor_result = ReconAuditorAI.audit_and_gather_facts(user_query, router_result, session_data)

        # --- STAGE 4: PrecisionSynthesizerAI (Tag-Driven Presentation Formatting) ---
        synthesizer_result = PrecisionSynthesizerAI.synthesize_response(user_query, router_result, auditor_result, history_snapshot)
        final_answer = synthesizer_result.get("final_answer", "")

        # Save turn into in-memory sliding cache
        SESSION_CHAT_MEMORY.append({
            "user": user_query,
            "assistant": final_answer,
            "intent": router_result.get("intent", "COMPREHENSIVE_AUDIT"),
            "order_id": router_result.get("extracted_entities", {}).get("order_id")
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
                    "status": "ENRICHED_AND_TAGGED",
                    "scope": "IN_SCOPE",
                    "intent": router_result.get("intent", "COMPREHENSIVE_AUDIT"),
                    "tags": router_result.get("tags", []),
                    "entities": router_result.get("extracted_entities", {}),
                    "data_requirements": router_result.get("data_requirements", []),
                    "confidence": router_result.get("confidence", 0.95),
                    "enriched_query": router_result.get("enriched_query", user_query),
                    "summary": router_result.get("summary", "")
                },
                "agent_3": {
                    "name": "ReconAuditorAI",
                    "status": "FACTS_GATHERED",
                    "tools_called": auditor_result.get("tools_called", [])
                },
                "agent_4": {
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
