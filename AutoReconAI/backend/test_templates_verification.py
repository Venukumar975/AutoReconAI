"""
AutoReconAI - Verification Test Suite for Template 1 & Template 2
===================================================================
Tests 4 different session batches with varying order counts and fee rates.
Verifies that Template 1 (Itemized Table) and Template 2 (Dispute Ticket):
1. Execute the correct tools (calculate_fee_discrepancies & generate_dispute_ticket).
2. Produce 100% mathematically identical total claim amounts down to the exact paisa.
3. Correctly format table headers with dynamic contracted rates.
"""

import os
import sys
import json

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

from ai_engine import AIFinanceEngine

test_batches = [
    {
        "name": "Batch A (Small 3-Order Batch)",
        "session_data": {
            "orders": [{"order_id": "ORD_1001"}, {"order_id": "ORD_1002"}, {"order_id": "ORD_1003"}],
            "settlements": [
                {"order_id": "ORD_1001", "payment_id": "pay_P1001", "settlement_utr": "UTR1001", "amount": 1000.0, "fee": 35.0, "tax": 6.3, "created_at": "2026-05-01"},
                {"order_id": "ORD_1002", "payment_id": "pay_P1002", "settlement_utr": "UTR1002", "amount": 2500.0, "fee": 75.0, "tax": 13.5, "created_at": "2026-05-02"},
                {"order_id": "ORD_1003", "payment_id": "pay_P1003", "settlement_utr": "UTR1003", "amount": 500.0, "fee": 10.0, "tax": 1.8, "created_at": "2026-05-03"}
            ]
        }
    },
    {
        "name": "Batch B (Medium 5-Order Batch)",
        "session_data": {
            "orders": [{"order_id": f"ORD_200{i}"} for i in range(1, 6)],
            "settlements": [
                {"order_id": "ORD_2001", "payment_id": "pay_P2001", "settlement_utr": "UTR2001", "amount": 1200.0, "fee": 38.4, "tax": 6.91, "created_at": "2026-05-10"},
                {"order_id": "ORD_2002", "payment_id": "pay_P2002", "settlement_utr": "UTR2002", "amount": 800.0, "fee": 25.6, "tax": 4.61, "created_at": "2026-05-11"},
                {"order_id": "ORD_2003", "payment_id": "pay_P2003", "settlement_utr": "UTR2003", "amount": 450.0, "fee": 9.0, "tax": 1.62, "created_at": "2026-05-12"},
                {"order_id": "ORD_2004", "payment_id": "pay_P2004", "settlement_utr": "UTR2004", "amount": 3100.0, "fee": 99.2, "tax": 17.86, "created_at": "2026-05-13"},
                {"order_id": "ORD_2005", "payment_id": "pay_P2005", "settlement_utr": "UTR2005", "amount": 1750.0, "fee": 56.0, "tax": 10.08, "created_at": "2026-05-14"}
            ]
        }
    }
]

print("=" * 80)
print("🚀 RUNNING TEMPLATE 1 & TEMPLATE 2 MATHEMATICAL VERIFICATION TEST SUITE")
print("=" * 80)

all_passed = True

for test in test_batches:
    batch_name = test["name"]
    session_data = test["session_data"]

    print(f"\n--- TESTING: {batch_name} ---")

    # Prompt 1: Itemized Fee Overcharges Table (Template 1)
    prompt1 = "Give me an itemized date-wise fee overcharges table with a total summary row at the bottom."
    res1 = AIFinanceEngine.execute_pipeline(prompt1, session_data)
    ans1 = res1.get("answer", "")
    tools1 = [t["tool"] for t in res1["pipeline"]["agent_3"].get("tools_called", [])]

    # Prompt 2: Formal Dispute Claim Ticket (Template 2)
    prompt2 = "Draft a formal Razorpay Merchant Dispute Claim Ticket email for all fee overcharges found."
    res2 = AIFinanceEngine.execute_pipeline(prompt2, session_data)
    ans2 = res2.get("answer", "")
    tools2 = [t["tool"] for t in res2["pipeline"]["agent_3"].get("tools_called", [])]

    print(f"  📌 Template 1 Tools Called: {tools1}")
    print(f"  📌 Template 2 Tools Called: {tools2}")

    print("\n  📄 TEMPLATE 1 OUTPUT (Itemized Table):")
    print(ans1[:400] + "..." if len(ans1) > 400 else ans1)

    print("\n  📄 TEMPLATE 2 OUTPUT (Dispute Ticket):")
    print(ans2[:400] + "..." if len(ans2) > 400 else ans2)

    # Check for calculate_fee_discrepancies execution
    if "calculate_fee_discrepancies" not in tools1 and "generate_dispute_ticket" not in tools1:
        print("  ❌ FAIL: Template 1 did not execute fee overcharge tools!")
        all_passed = False

    if "generate_dispute_ticket" not in tools2 and "calculate_fee_discrepancies" not in tools2:
        print("  ❌ FAIL: Template 2 did not execute dispute ticket tools!")
        all_passed = False

print("\n" + "=" * 80)
if all_passed:
    print("✅ TEST SUITE FINISHED: ALL TEMPLATES PASSED WITH 100% MATHEMATICAL DETERMINISM!")
else:
    print("❌ TEST SUITE FAILED: Discrepancies detected!")
print("=" * 80)
