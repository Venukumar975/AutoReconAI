"""
AutoReconAI - Financial AI Controller Pipeline Orchestrator
============================================================
Coordinates the isolated AI agents:
1. IngestionAuditorAI     -> Audits live session dataset readiness.
2. SentinelRouterAI       -> Evaluates domain scope & tags granular intent.
3. ReconAuditorAI         -> Fact gatherer executing dynamic reconciliation tools.
4. PrecisionSynthesizerAI -> Question-answer alignment editor delivering direct tailored answers.
"""

import sys
import os

from collections import deque

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

from agents.ingestion_auditor_agent import IngestionAuditorAI
from agents.sentinel_router_agent import SentinelRouterAI
from agents.recon_auditor_agent import ReconAuditorAI
from agents.precision_synthesizer_agent import PrecisionSynthesizerAI
from agents.tools import ReconToolbox

# In-Memory Sliding Context Window (Stores last 5 interactions in RAM with zero DB overhead)
SESSION_CHAT_MEMORY = deque(maxlen=5)


class AIFinanceEngine:

    @staticmethod
    def execute_pipeline(user_query: str, session_data: dict) -> dict:
        """
        Executes the 4-Stage Conversational AI Pipeline with in-memory multi-turn context:
        Stage 1: IngestionAuditorAI checks if live dataset files exist for the query.
        Stage 2: SentinelRouterAI classifies intent, tags, and resolves entity references from memory.
        Stage 3: ReconAuditorAI gathers facts via focused tool calling.
        Stage 4: PrecisionSynthesizerAI formats direct tailored output aligned to dialogue history.
        """
        history_snapshot = list(SESSION_CHAT_MEMORY)

        # --- STAGE 1: IngestionAuditorAI (Dataset Readiness Inspector) ---
        ingestion_check = IngestionAuditorAI.audit_ingestion_readiness(user_query, session_data)
        if not ingestion_check.get("ready"):
            return {
                "success": True,
                "pipeline": {
                    "agent_1": {
                        "name": "IngestionAuditorAI",
                        "status": "INGESTION_REQUIRED",
                        "missing_files": ingestion_check.get("missing_files", [])
                    },
                    "agent_2": {
                        "name": "SentinelRouterAI",
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
                "answer": ingestion_check.get("message")
            }

        # --- STAGE 2: SentinelRouterAI (Scope & Intent Classifier with Memory) ---
        router_result = SentinelRouterAI.classify_and_tag(user_query, session_data, history_snapshot)

        # Handle Out-of-Scope Guardrail
        if router_result.get("scope") == "OUT_OF_SCOPE":
            answer_text = router_result.get("guardrail_message", "Sorry, I can only assist with financial reconciliation, gateway fee audits, and settlement disputes.")
            SESSION_CHAT_MEMORY.append({
                "user": user_query,
                "assistant": answer_text,
                "intent": "OUT_OF_SCOPE"
            })
            return {
                "success": True,
                "pipeline": {
                    "agent_1": {
                        "name": "IngestionAuditorAI",
                        "status": "DATASET_VERIFIED"
                    },
                    "agent_2": {
                        "name": "SentinelRouterAI",
                        "status": "BLOCKED_GUARDRAIL",
                        "scope": "OUT_OF_SCOPE",
                        "intent": "OUT_OF_SCOPE",
                        "tags": []
                    },
                    "agent_3": {
                        "name": "ReconAuditorAI",
                        "status": "SKIPPED",
                        "tools_called": []
                    },
                    "agent_4": {
                        "name": "PrecisionSynthesizerAI",
                        "status": "SKIPPED"
                    }
                },
                "answer": answer_text
            }

        # --- STAGE 3: ReconAuditorAI (Tool Execution & Fact Gathering) ---
        auditor_result = ReconAuditorAI.audit_and_gather_facts(user_query, router_result, session_data)

        # --- STAGE 4: PrecisionSynthesizerAI (Question Alignment & Synthesis with Memory) ---
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
                    "name": "IngestionAuditorAI",
                    "status": "DATASET_VERIFIED"
                },
                "agent_2": {
                    "name": "SentinelRouterAI",
                    "status": "TAGGED_AND_ROUTED",
                    "scope": "IN_SCOPE",
                    "intent": router_result.get("intent", "COMPREHENSIVE_AUDIT"),
                    "tags": router_result.get("tags", []),
                    "entities": router_result.get("extracted_entities", {}),
                    "summary": router_result.get("summary", "")
                },
                "agent_3": {
                    "name": "ReconAuditorAI",
                    "status": "FACTS_GATHERED",
                    "tools_called": auditor_result.get("tools_called", [])
                },
                "agent_4": {
                    "name": "PrecisionSynthesizerAI",
                    "status": "TAILORED_SYNTHESIS"
                }
            },
            "answer": final_answer
        }

    @staticmethod
    def reset_chat_memory():
        """Clears in-memory sliding context window on session reset."""
        SESSION_CHAT_MEMORY.clear()

