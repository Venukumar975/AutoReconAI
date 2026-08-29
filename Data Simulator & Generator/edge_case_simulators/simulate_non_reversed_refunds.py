"""
Edge Case Simulator 3: Dynamic Non-Reversed Refund Fees (Razorpay Refund Policy)
================================================================================
Simulates customer refunds where:
1. Full gross order amount is refunded to customer (-refund_amount net_credit debit).
2. Razorpay DOES NOT REVERSE the original MDR fee + 18% GST charged on payment capture.
3. Calculates exact un-reversed fee & GST overhead loss (fee + tax) dynamically without static hardcoding.
"""

from datetime import datetime, timedelta
import random
import sqlite3

def apply_non_reversed_refunds_simulation(db_path, orphan_refund_count, base_mdr=0.02, gst_rate=0.18):
    if orphan_refund_count <= 0:
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT settlement_utr FROM payments WHERE settlement_utr IS NOT NULL ORDER BY RANDOM() LIMIT 1;")
    ref_row = cursor.fetchone()
    utr_target = ref_row["settlement_utr"] if ref_row else "CMS2026052099"

    # Fetch real orders from store.db to refund their EXACT real order amounts!
    cursor.execute("SELECT order_id, gross_amount, created_at FROM orders WHERE order_status = 'FULFILLED' ORDER BY RANDOM() LIMIT ?;", (orphan_refund_count,))
    real_orders = cursor.fetchall()

    if not real_orders:
        conn.close()
        return []

    refunded_details = []

    for i, t_order in enumerate(real_orders, 1):
        refund_id = f"rfnd_R{random.randint(1000, 9999)}"
        payment_id = f"pay_P{random.randint(1000, 9999)}"

        refund_amount = float(t_order["gross_amount"])
        base_date_str = str(t_order["created_at"])[:10] if t_order["created_at"] else "2026-05-15"

        retained_mdr = round(refund_amount * base_mdr, 2)
        retained_gst = round(retained_mdr * gst_rate, 2)
        unreversed_loss = round(retained_mdr + retained_gst, 2)
        net_credit = -refund_amount

        # Alternate: Even index = Same-Day Refund (same date as order), Odd index = Prior-Date Refund (T+10 Days Offset)
        is_same_day = (i % 2 == 0)

        if is_same_day:
            oid = t_order["order_id"]
            refund_date = base_date_str
            date_label = f"Same-Day Refund (Date: {refund_date})"

            # Explicit SQL 1: Update store orders table status
            cursor.execute("""
                UPDATE orders 
                SET order_status = 'CANCELLED_REFUNDED' 
                WHERE order_id = ?;
            """, (oid,))

            # Explicit SQL 2: Insert new refund payout entry into gateway payments table
            cursor.execute("""
                INSERT INTO payments (
                    payment_id, order_id, amount, fee, tax, net_credit, settlement_utr, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'refunded');
            """, (payment_id, oid, refund_amount, retained_mdr, retained_gst, net_credit, utr_target))

        else:
            oid = f"ORD_PRIOR_{900 + i}"
            try:
                base_dt = datetime.strptime(base_date_str, "%Y-%m-%d")
                offset_dt = base_dt + timedelta(days=random.randint(7, 15))
                refund_date = offset_dt.strftime("%Y-%m-%d")
            except Exception:
                refund_date = "2026-05-25"
            date_label = f"Prior-Date Refund (Date: {refund_date}, T+10 Days Offset from Sale)"

            # Explicit SQL: Insert prior refund payout entry into gateway payments table (Store table untouched)
            cursor.execute("""
                INSERT INTO payments (
                    payment_id, order_id, amount, fee, tax, net_credit, settlement_utr, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'refunded');
            """, (payment_id, oid, refund_amount, retained_mdr, retained_gst, net_credit, utr_target))

        refunded_details.append({
            "refund_id": refund_id,
            "order_id": oid,
            "type": date_label,
            "refund_date": refund_date,
            "refund_amount": refund_amount,
            "retained_mdr": retained_mdr,
            "retained_gst": retained_gst,
            "unreversed_loss": unreversed_loss,
            "utr": utr_target
        })

    conn.commit()
    conn.close()

    print(f"[EDGE CASE 3] Non-Reversed Refund Fees: Generated {len(refunded_details)} dynamic refunds with explicit T+10 date offsets.")
    return refunded_details
