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

    # 1. Fetch real orders JOINED with their original payment UTR and created_at date
    cursor.execute("""
        SELECT o.order_id, o.gross_amount, o.created_at, p.settlement_utr 
        FROM orders o
        JOIN payments p ON o.order_id = p.order_id
        WHERE o.order_status = 'FULFILLED' AND p.settlement_utr IS NOT NULL
        ORDER BY RANDOM() LIMIT ?;
    """, (orphan_refund_count,))
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
        orig_utr = t_order["settlement_utr"]

        retained_mdr = round(refund_amount * base_mdr, 2)
        retained_gst = round(retained_mdr * gst_rate, 2)
        unreversed_loss = round(retained_mdr + retained_gst, 2)
        net_credit = -refund_amount

        # Alternate: Even index = Same-Day Refund, Odd index = Prior-Date Refund (T+1 to T+9 Days Offset)
        is_same_day = (i % 2 == 0)

        if is_same_day:
            # SAME-DAY REFUND: Use the exact SAME order ID, date, and UTR of original payment!
            oid = t_order["order_id"]
            refund_date = base_date_str
            target_utr = orig_utr  # Exact same UTR as the payment on the same day!
            date_label = f"Same-Day Refund (Date: {refund_date}, UTR: {target_utr})"

            # Update store orders status
            cursor.execute("""
                UPDATE orders 
                SET order_status = 'CANCELLED_REFUNDED' 
                WHERE order_id = ?;
            """, (oid,))

            # Insert refund entry into payments table under the SAME UTR!
            cursor.execute("""
                INSERT INTO payments (
                    payment_id, order_id, amount, fee, tax, net_credit, settlement_utr, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'refunded');
            """, (payment_id, oid, refund_amount, retained_mdr, retained_gst, net_credit, target_utr))

        else:
            # PRIOR-DATE REFUND: Add random date offset (T+1 to T+9 days)
            oid = f"ORD_PRIOR_{900 + i}"
            offset_days = random.randint(1, 9)
            try:
                base_dt = datetime.strptime(base_date_str, "%Y-%m-%d")
                offset_dt = base_dt + timedelta(days=offset_days)
                refund_date = offset_dt.strftime("%Y-%m-%d")
            except Exception:
                refund_date = "2026-05-25"

            # Check if this offset date is present in our database's settlement payments
            cursor.execute("""
                SELECT p.settlement_utr 
                FROM payments p
                JOIN orders o ON p.order_id = o.order_id
                WHERE DATE(o.created_at) = ? AND p.settlement_utr IS NOT NULL
                LIMIT 1;
            """, (refund_date,))
            matched_utr_row = cursor.fetchone()

            if matched_utr_row and matched_utr_row["settlement_utr"]:
                # Date present in table! Use that settlement batch's UTR!
                target_utr = matched_utr_row["settlement_utr"]
            else:
                # Date not present! Create a new UTR for this settlement date!
                clean_date_str = refund_date.replace("-", "")
                target_utr = f"CMS{clean_date_str}{random.randint(1000, 9999)}"

            date_label = f"Prior-Date Refund (Date: {refund_date}, UTR: {target_utr}, Offset: T+{offset_days} Days)"

            # Insert prior refund entry into payments table under the target date's UTR!
            cursor.execute("""
                INSERT INTO payments (
                    payment_id, order_id, amount, fee, tax, net_credit, settlement_utr, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'refunded');
            """, (payment_id, oid, refund_amount, retained_mdr, retained_gst, net_credit, target_utr))

        refunded_details.append({
            "refund_id": refund_id,
            "order_id": oid,
            "type": date_label,
            "refund_date": refund_date,
            "refund_amount": refund_amount,
            "retained_mdr": retained_mdr,
            "retained_gst": retained_gst,
            "unreversed_loss": unreversed_loss,
            "utr": target_utr
        })

    conn.commit()
    conn.close()

    print(f"[EDGE CASE 3] Non-Reversed Refund Fees: Generated {len(refunded_details)} dynamic refunds mapped to date-matching settlement UTRs.")
    return refunded_details
