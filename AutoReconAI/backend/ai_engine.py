"""
AutoReconAI - 4-Agent Financial AI Controller Pipeline Orchestrator
===================================================================
Coordinates the 4 isolated AI agents:
0. IngestionAuditorAI     -> Audits live session dataset readiness.
1. SentinelRouterAI       -> Evaluates domain scope & tags granular intent.
2. ReconAuditorAI         -> Fact gatherer executing dynamic reconciliation tools.
3. PrecisionSynthesizerAI -> Question-answer alignment editor delivering direct tailored answers.
"""

import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

from agents.ingestion_auditor_agent import IngestionAuditorAI
from agents.sentinel_router_agent import SentinelRouterAI
from agents.recon_auditor_agent import ReconAuditorAI
from agents.precision_synthesizer_agent import PrecisionSynthesizerAI
from agents.tools import ReconToolbox


class AIFinanceEngine:

    @staticmethod
    def execute_pipeline(user_query: str, session_data: dict) -> dict:
        """
        Executes the 4-Agent AI Pipeline:
        Stage 0: IngestionAuditorAI checks if live dataset files exist for the query.
        Stage 1: SentinelRouterAI classifies intent, tags, and validates scope.
        Stage 2: ReconAuditorAI gathers facts via tool calling.
        Stage 3: PrecisionSynthesizerAI formats direct tailored output aligned to user query.
        """
        # --- STAGE 0: IngestionAuditorAI (Dataset Readiness Inspector) ---
        ingestion_check = IngestionAuditorAI.audit_ingestion_readiness(user_query, session_data)
        if not ingestion_check.get("ready"):
            return {
                "success": True,
                "pipeline": {
                    "agent_0": {
                        "name": "IngestionAuditorAI",
                        "status": "INGESTION_REQUIRED",
                        "missing_files": ingestion_check.get("missing_files", [])
                    },
                    "agent_1": {
                        "name": "SentinelRouterAI",
                        "status": "SKIPPED"
                    },
                    "agent_2": {
                        "name": "ReconAuditorAI",
                        "status": "SKIPPED"
                    },
                    "agent_3": {
                        "name": "PrecisionSynthesizerAI",
                        "status": "SKIPPED"
                    }
                },
                "answer": ingestion_check.get("message")
            }

        # --- STAGE 1: SentinelRouterAI (Scope & Intent Classifier) ---
        router_result = SentinelRouterAI.classify_and_tag(user_query, session_data)

        # Handle Out-of-Scope Guardrail (Simple clean message, no alert cards)
        if router_result.get("scope") == "OUT_OF_SCOPE":
            return {
                "success": True,
                "pipeline": {
                    "agent_1": {
                        "name": "SentinelRouterAI",
                        "status": "BLOCKED_GUARDRAIL",
                        "scope": "OUT_OF_SCOPE",
                        "intent": "OUT_OF_SCOPE",
                        "tags": []
                    },
                    "agent_2": {
                        "name": "ReconAuditorAI",
                        "status": "SKIPPED",
                        "tools_called": []
                    },
                    "agent_3": {
                        "name": "PrecisionSynthesizerAI",
                        "status": "SKIPPED"
                    }
                },
                "answer": router_result.get("guardrail_message", "Sorry, I can only assist with financial reconciliation, gateway fee audits, and settlement disputes.")
            }

        # --- STAGE 2: ReconAuditorAI (Tool Execution & Fact Gathering) ---
        auditor_result = ReconAuditorAI.audit_and_gather_facts(user_query, router_result, session_data)

        # --- STAGE 3: PrecisionSynthesizerAI (Question Alignment & Synthesis) ---
        synthesizer_result = PrecisionSynthesizerAI.synthesize_response(user_query, router_result, auditor_result)

        return {
            "success": True,
            "pipeline": {
                "agent_0": {
                    "name": "IngestionAuditorAI",
                    "status": "DATASET_VERIFIED"
                },
                "agent_1": {
                    "name": "SentinelRouterAI",
                    "status": "TAGGED_AND_ROUTED",
                    "scope": "IN_SCOPE",
                    "intent": router_result.get("intent", "COMPREHENSIVE_AUDIT"),
                    "tags": router_result.get("tags", []),
                    "entities": router_result.get("extracted_entities", {}),
                    "summary": router_result.get("summary", "")
                },
                "agent_2": {
                    "name": "ReconAuditorAI",
                    "status": "FACTS_GATHERED",
                    "tools_called": auditor_result.get("tools_called", [])
                },
                "agent_3": {
                    "name": "PrecisionSynthesizerAI",
                    "status": "TAILORED_SYNTHESIS"
                }
            },
            "answer": synthesizer_result.get("final_answer", "")
        }
