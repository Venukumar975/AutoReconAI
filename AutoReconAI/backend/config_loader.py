"""
AutoReconAI - Central Configuration & SLA Blueprint Loader
===========================================================
Reads the master `config.ini` dynamically so that any changes to MDR rates,
GST rates, or edge case settings are immediately reflected across:
1. Razorpay Gateway Server (payment billing)
2. AutoReconAI 3-Way Reconciliation Math & Verification Tools
3. All 4 AI Agents (IngestionAuditor, SentinelRouter, ReconAuditor, PrecisionSynthesizer)
"""

import os
import configparser

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Locate config.ini in 'Data Simulator & Generator' or fallback to root
CONFIG_PATHS = [
    os.path.join(CURRENT_DIR, "..", "..", "Data Simulator & Generator", "config.ini"),
    os.path.join(CURRENT_DIR, "..", "config.ini"),
    os.path.join(CURRENT_DIR, "config.ini")
]


def load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    for path in CONFIG_PATHS:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            config.read(abs_path, encoding="utf-8")
            return config
    return config


class GatewayConfig:

    @staticmethod
    def get_mdr_rate() -> float:
        """Returns contracted MDR rate as decimal (e.g. 0.02 for 2.0%)."""
        config = load_config()
        try:
            percent = float(config.get("CONTRACTED_RATES", "mdr_rate_percent", fallback=2.0))
            return percent / 100.0
        except Exception:
            return 0.02

    @staticmethod
    def get_gst_rate() -> float:
        """Returns GST rate as decimal (e.g. 0.18 for 18.0%)."""
        config = load_config()
        try:
            percent = float(config.get("CONTRACTED_RATES", "gst_rate_percent", fallback=18.0))
            return percent / 100.0
        except Exception:
            return 0.18

    @staticmethod
    def get_effective_sla_rate() -> float:
        """Returns total effective fee rate: MDR * (1 + GST) (e.g. 0.0236 for 2.36%)."""
        mdr = GatewayConfig.get_mdr_rate()
        gst = GatewayConfig.get_gst_rate()
        return mdr * (1.0 + gst)

    @staticmethod
    def get_sla_text() -> str:
        """Returns clean human-readable SLA text for AI agent system prompts."""
        mdr_pct = GatewayConfig.get_mdr_rate() * 100.0
        gst_pct = GatewayConfig.get_gst_rate() * 100.0
        eff_pct = GatewayConfig.get_effective_sla_rate() * 100.0
        return f"{mdr_pct:.2f}% Domestic MDR + {gst_pct:.2f}% GST (Total Effective {eff_pct:.2f}%)"

    @staticmethod
    def get_edge_case_config() -> dict:
        config = load_config()
        try:
            return {
                "enable_edge_cases": config.getboolean("EDGE_CASES", "enable_edge_cases", fallback=True),
                "dropped_webhook_count": int(config.get("EDGE_CASES", "dropped_webhook_count", fallback=3)),
                "fee_overcharge_count": int(config.get("EDGE_CASES", "fee_overcharge_count", fallback=3)),
                "orphan_refund_count": int(config.get("EDGE_CASES", "orphan_refund_count", fallback=2))
            }
        except Exception:
            return {
                "enable_edge_cases": True,
                "dropped_webhook_count": 3,
                "fee_overcharge_count": 3,
                "orphan_refund_count": 2
            }
