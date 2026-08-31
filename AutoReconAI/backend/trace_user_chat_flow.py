"""
Test Script for Commit 9daf27a Codebase
========================================
Executes the user's exact chat interaction on commit 9daf27a code.
"""

import os
import sys
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

from ai_engine import AIFinanceEngine
from parsers.csv_parser import parse_orders_csv, parse_settlement_csv
from parsers.excel_parser import detect_and_extract_excel_table, parse_mapped_excel_transactions

def load_session_data():
    gen_dir = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "generated_data"))
    orders_csv = os.path.join(gen_dir, "store_orders.csv")
    settlement_csv = os.path.join(gen_dir, "razorpay_settlement_recon.csv")
    bank_excel = os.path.join(gen_dir, "bank_statement_union_bank.xlsx")

    orders = parse_orders_csv(orders_csv) if os.path.exists(orders_csv) else []
    settlements = parse_settlement_csv(settlement_csv) if os.path.exists(settlement_csv) else []

    bank_txns = []
    if os.path.exists(bank_excel):
        headers, preview, all_rows, op_bal = detect_and_extract_excel_table(bank_excel)
        mapping = {
            "txn_date": "Txn Date",
            "primary_narration": "Narration / Description",
            "secondary_narration": "Reference No",
            "debit": "Withdrawal (Debit)",
            "credit": "Deposit (Credit)",
            "balance": "Closing Balance"
        }
        bank_txns = parse_mapped_excel_transactions(all_rows, mapping, headers)

    return {
        "orders": orders,
        "settlements": settlements,
        "bank_txns": bank_txns
    }

def run_tests_on_commit_9daf27a():
    print("=" * 80, flush=True)
    print("🚀 RUNNING MULTI-TURN CHAT TESTS ON COMMIT 9daf27a CODEBASE", flush=True)
    print("=" * 80, flush=True)

    session_data = load_session_data()
    AIFinanceEngine.reset_chat_memory()

    user_prompts = [
        "Audit reconciliation batch and explain all mismatches across the 3 categories.",
        "did i lost moeny or what",
        "hey did i lost my amount",
        "how much amount si recoverabel",
        "so once i recover this amount is there any other amount i need to recover",
        "i want the complete description of order id 1063",
        "i want a complete desc about this order",
        "i want customer details too",
        "ok tell me did i lost any other amount permenantly"
    ]

    for idx, prompt in enumerate(user_prompts, 1):
        print(f"\n--------------------------------------------------------------------------------", flush=True)
        print(f"[{idx}/9] 👤 USER QUERY: \"{prompt}\"", flush=True)

        res = AIFinanceEngine.execute_pipeline(prompt, session_data)
        p = res.get("pipeline", {})
        a1 = p.get("agent_1", {})
        a2 = p.get("agent_2", {})
        a3 = p.get("agent_3", {})

        print(f"🛡️ [Agent 1 - SentinelFirewallAI] : Status = {a1.get('status')}", flush=True)
        print(f"🧠 [Agent 2 - DomainReasonerAI]   : Status = {a2.get('status')}, Tools Called = {[t.get('tool') for t in a2.get('tools_called', [])]}", flush=True)
        if a2.get('summary'):
            print(f"   ↳ Summary                   : \"{a2.get('summary')[:90]}...\"", flush=True)
        print(f"✍️ [Agent 3 - PrecisionSynthesizer]: Status = {a3.get('status')}", flush=True)
        print(f"\n💬 Output Answer:\n{res.get('answer', '')}\n", flush=True)

    print("=" * 80, flush=True)
    print("✅ TEST RUN ON COMMIT 9daf27a FINISHED!", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    run_tests_on_commit_9daf27a()
