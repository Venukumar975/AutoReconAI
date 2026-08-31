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
    def is_tds_applicable() -> bool:
        """Returns True if Section 194-O TDS is active, False otherwise."""
        config = load_config()
        try:
            val = config.get("MERCHANT_TAX_PROFILE", "is_tds_applicable", fallback="no").strip().lower()
            return val in ["yes", "true", "1", "y"]
        except Exception:
            return False

    @staticmethod
    def get_tds_rate() -> float:
        """Returns Section 194-O TDS rate as decimal (e.g. 0.01 for 1.0%)."""
        config = load_config()
        try:
            percent = float(config.get("MERCHANT_TAX_PROFILE", "tds_rate_percent", fallback=1.0))
            return percent / 100.0
        except Exception:
            return 0.01

    @staticmethod
    def get_merchant_tax_profile() -> dict:
        """Returns statutory tax identifiers (GSTIN, PAN)."""
        config = load_config()
        try:
            return {
                "gstin": config.get("MERCHANT_TAX_PROFILE", "gstin", fallback="36AATUF1234F1ZV"),
                "pan": config.get("MERCHANT_TAX_PROFILE", "pan", fallback="ABCDE1234F"),
                "is_tds_applicable": GatewayConfig.is_tds_applicable(),
                "tds_rate_percent": GatewayConfig.get_tds_rate() * 100.0
            }
        except Exception:
            return {
                "gstin": "36AATUF1234F1ZV",
                "pan": "ABCDE1234F",
                "is_tds_applicable": False,
                "tds_rate_percent": 1.0
            }

    @staticmethod
    def get_edge_case_config() -> dict:
        config = load_config()
        try:
            return {
                "enable_edge_cases": config.getboolean("EDGE_CASES", "enable_edge_cases", fallback=True),
                "dropped_webhook_count": int(config.get("EDGE_CASES", "dropped_webhook_count", fallback=2)),
                "fee_overcharge_count": int(config.get("EDGE_CASES", "fee_overcharge_count", fallback=2)),
                "orphan_refund_count": int(config.get("EDGE_CASES", "orphan_refund_count", fallback=2)),
                "chargeback_hold_count": int(config.get("EDGE_CASES", "chargeback_hold_count", fallback=1))
            }
        except Exception:
            return {
                "enable_edge_cases": True,
                "dropped_webhook_count": 2,
                "fee_overcharge_count": 2,
                "orphan_refund_count": 2,
                "chargeback_hold_count": 1
            }


MODEL_PATHS = [
    os.path.join(CURRENT_DIR, "..", "..", "ai_models.ini"),
    os.path.join(CURRENT_DIR, "..", "ai_models.ini"),
    os.path.join(CURRENT_DIR, "ai_models.ini")
]


def load_model_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    for path in MODEL_PATHS:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            config.read(abs_path, encoding="utf-8")
            return config
    return config


class ModelConfig:

    @staticmethod
    def get_primary_model() -> str:
        """Returns primary Gemini model from ai_models.ini or environment variable."""
        env_model = os.getenv("GEMINI_MODEL")
        if env_model:
            return env_model.strip()

        config = load_model_config()
        try:
            return config.get("GEMINI_MODELS", "primary_model", fallback="gemini-3.6-flash").strip()
        except Exception:
            return "gemini-3.6-flash"

    @staticmethod
    def get_model_fallback_chain() -> list:
        """
        Returns an ordered list of Gemini model candidates.
        Ensures zero-downtime automatic fallback if any model name is sunset or rate-limited.
        """
        candidates = []

        # 1. Environment variable override if present
        env_model = os.getenv("GEMINI_MODEL")
        if env_model:
            candidates.append(env_model.strip())

        config = load_model_config()
        if config.has_section("GEMINI_MODELS"):
            for key, val in config.items("GEMINI_MODELS"):
                clean_val = val.strip()
                if clean_val and clean_val not in candidates:
                    candidates.append(clean_val)

        # 2. Hardcoded resilient default fallbacks
        defaults = ["gemini-3.6-flash", "gemini-1.5-flash", "gemini-2.5-pro", "gemini-1.5-pro", "gemini-pro"]
        for d in defaults:
            if d not in candidates:
                candidates.append(d)

        return candidates

