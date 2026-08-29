"""
Edge Case Simulator 2: Gateway Fee Overcharges (MDR SLA Breaches)
===================================================================
Simulates payment gateway fee overbilling by billing N random payments
at rates exceeding active contracted SLA terms (e.g. 2.65% to 2.85% MDR).
"""

import random
import sqlite3

def apply_fee_overcharges_simulation(db_path, fee_overcharge_count, base_mdr=0.02, gst_rate=0.18):
    if fee_overcharge_count <= 0:
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT payment_id, amount FROM payments ORDER BY RANDOM() LIMIT ?;", (fee_overcharge_count,))
    target_payments = cursor.fetchall()
    overcharged_ids = []

    for p in target_payments:
        amt = p["amount"]
        overcharge_rate = base_mdr + random.uniform(0.005, 0.0085)
        fee = round(amt * overcharge_rate, 2)
        tax = round(fee * gst_rate, 2)
        net_credit = round(amt - fee - tax, 2)

        cursor.execute("""
            UPDATE payments 
            SET fee = ?, tax = ?, net_credit = ? 
            WHERE payment_id = ?;
        """, (fee, tax, net_credit, p["payment_id"]))
        overcharged_ids.append(p["payment_id"])

    conn.commit()
    conn.close()

    print(f"[EDGE CASE 2] Fee Overcharges: Overcharged {len(overcharged_ids)} payments above {base_mdr*100:.2f}% MDR threshold.")
    return overcharged_ids
