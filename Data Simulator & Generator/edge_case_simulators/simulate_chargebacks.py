"""
Edge Case Simulator 4: Customer Chargeback & Dispute Fee Hold (Razorpay Bank Dispute)
======================================================================================
Simulates customer chargebacks raised directly with issuing banks (SBI/HDFC/Visa):
1. The store order remains 'FULFILLED' (goods were packaged and delivered).
2. Razorpay forcefully holds/debits the gross order amount from today's settlement payout.
3. Razorpay charges a non-refundable administrative Dispute Fee (₹500.00 + 18% GST = ₹590.00).
4. Net settlement debit = -(Gross Order Amount + Dispute Fee + GST).
"""

import random
import sqlite3


def apply_chargebacks_simulation(db_path, chargeback_count, dispute_fee=500.0, gst_rate=0.18):
    if chargeback_count <= 0:
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Fetch real fulfilled orders joined with their payment UTR and date
    cursor.execute("""
        SELECT o.order_id, o.gross_amount, o.created_at, p.settlement_utr 
        FROM orders o
        JOIN payments p ON o.order_id = p.order_id
        WHERE o.order_status = 'FULFILLED' 
          AND p.settlement_utr IS NOT NULL 
          AND p.status = 'captured'
        ORDER BY RANDOM() LIMIT ?;
    """, (chargeback_count,))
    target_orders = cursor.fetchall()

    if not target_orders:
        conn.close()
        return []

    chargeback_details = []

    for t_order in target_orders:
        oid = t_order["order_id"]
        gross_amount = float(t_order["gross_amount"])
        settlement_utr = t_order["settlement_utr"]
        created_at = str(t_order["created_at"])[:10] if t_order["created_at"] else "2026-05-15"

        dispute_id = f"disp_D{random.randint(1000, 9999)}"
        fee_amt = round(dispute_fee, 2)
        tax_amt = round(fee_amt * gst_rate, 2)
        total_penalty = round(fee_amt + tax_amt, 2)
        net_credit_debit = -round(gross_amount + total_penalty, 2)

        # Store order stays FULFILLED! (Merchant shipped the order)
        # We insert a dispute_hold debit transaction in payments table under the SAME UTR batch
        cursor.execute("""
            INSERT INTO payments (
                payment_id, order_id, amount, fee, tax, tds, net_credit, settlement_utr, status
            ) VALUES (?, ?, ?, ?, ?, 0.0, ?, ?, 'dispute_hold');
        """, (dispute_id, oid, gross_amount, fee_amt, tax_amt, net_credit_debit, settlement_utr))

        chargeback_details.append({
            "dispute_id": dispute_id,
            "order_id": oid,
            "disputed_order_amount": gross_amount,
            "dispute_fee": fee_amt,
            "dispute_tax": tax_amt,
            "total_dispute_penalty": total_penalty,
            "total_net_debit": net_credit_debit,
            "settlement_utr": settlement_utr,
            "date": created_at
        })

    conn.commit()
    conn.close()

    print(f"[EDGE CASE 4] Customer Chargebacks: Generated {len(chargeback_details)} dispute hold records (INR 500 fee + INR 90 GST debit each).")
    return chargeback_details
