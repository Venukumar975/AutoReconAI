"""
Edge Case Simulator 5: Section 194-O Statutory 1% TDS Upfront Deduction
========================================================================
Simulates Section 194-O of the Indian Income Tax Act:
1. When IS_TDS_APPLICABLE = 'yes' (or True):
   - Payment gateway deducts 1.00% TDS on Gross Sale value upfront.
   - Net settlement payout = Gross Amount - 2% MDR - 18% GST on MDR - 1% TDS.
   - Payout in bank statement matches this reduced amount.
2. When IS_TDS_APPLICABLE = 'no' (or False):
   - Standard settlement applies: Net Payout = Gross Amount - 2% MDR - 18% GST.
   - TDS = 0.00.
"""

import sqlite3


def apply_section_194o_tds_simulation(db_path, is_tds_applicable=False, tds_rate=0.01, gstin="36AATUF1234F1ZV", pan="ABCDE1234F"):
    """
    Applies Section 194-O Statutory TDS policy dynamically across payments in store.db:
    - If is_tds_applicable is False: Leaves standard net_credit (amount - fee - tax) with tds = 0.
    - If is_tds_applicable is True: Deducts 1.00% TDS on all captured orders, adjusting net_credit.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check if 'tds' column exists in payments table, add if missing
    cursor.execute("PRAGMA table_info(payments);")
    columns = [col[1] for col in cursor.fetchall()]
    if "tds" not in columns:
        cursor.execute("ALTER TABLE payments ADD COLUMN tds REAL DEFAULT 0.0;")
        conn.commit()

    if not is_tds_applicable:
        # PATH A: TDS NOT APPLICABLE
        # Ensure all captured payments are at standard formula (amount - fee - tax) and tds = 0
        cursor.execute("""
            UPDATE payments 
            SET tds = 0.0,
                net_credit = ROUND(amount - fee - tax, 2)
            WHERE status = 'captured';
        """)
        conn.commit()
        conn.close()

        print(f"[EDGE CASE 5] Section 194-O TDS: DISABLED (is_tds_applicable=no). Standard settlement formula applied (Gross - MDR - GST).")
        return {
            "status": "DISABLED",
            "is_tds_applicable": False,
            "total_tds_deducted": 0.0,
            "transactions_count": 0,
            "merchant_tax_profile": {
                "gstin": gstin,
                "pan": pan
            }
        }

    # PATH B: TDS APPLICABLE (1% Statutory Withholding)
    cursor.execute("""
        SELECT payment_id, amount, fee, tax 
        FROM payments 
        WHERE status = 'captured';
    """)
    captured_payments = cursor.fetchall()

    if not captured_payments:
        conn.close()
        return {
            "status": "NO_CAPTURED_PAYMENTS",
            "is_tds_applicable": True,
            "total_tds_deducted": 0.0,
            "transactions_count": 0
        }

    total_tds_sum = 0.0
    updated_count = 0

    for row in captured_payments:
        pid = row["payment_id"]
        amt = float(row["amount"])
        fee = float(row["fee"])
        tax = float(row["tax"])

        tds_amt = round(amt * tds_rate, 2)
        new_net_credit = round(amt - fee - tax - tds_amt, 2)
        total_tds_sum += tds_amt
        updated_count += 1

        cursor.execute("""
            UPDATE payments 
            SET tds = ?, net_credit = ? 
            WHERE payment_id = ?;
        """, (tds_amt, new_net_credit, pid))

    conn.commit()
    conn.close()

    print(f"[EDGE CASE 5] Section 194-O TDS: ENABLED (is_tds_applicable=yes). Withheld INR {total_tds_sum:,.2f} total TDS ({tds_rate*100:.1f}%) across {updated_count} captured transactions.")
    return {
        "status": "APPLIED",
        "is_tds_applicable": True,
        "tds_rate_percent": round(tds_rate * 100, 2),
        "total_tds_deducted": round(total_tds_sum, 2),
        "transactions_count": updated_count,
        "merchant_tax_profile": {
            "gstin": gstin,
            "pan": pan
        }
    }
