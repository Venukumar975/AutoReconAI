"""
Razorpay Payment Gateway Backend Service
========================================
Runs on port 5051 (http://127.0.0.1:5051).
Acts as the official Razorpay Payment Gateway backend:
1. Receives payment authorization requests from merchant websites.
2. Computes 2.0% MDR fee + 18% GST (or simulates fee overcharges).
3. Records captured transactions into the `payments` table in `store.db`.
4. Sends back an Acknowledgment (ACK) to the merchant server.
5. Can simulate Dropped Webhooks / Missed ACKs (Edge Case 1).
"""

import json
import os
import random
import sqlite3
import sys
import time
import traceback
from datetime import datetime
from flask import Flask, jsonify, request

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT_DIR, "store.db")
PORT = 5051

app = Flask(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/api/gateway/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "online",
        "service": "Razorpay Payment Gateway Engine",
        "port": PORT,
        "standard_mdr": "2.0%",
        "gst_rate": "18.0%"
    })


@app.route("/api/gateway/pay", methods=["POST"])
def process_payment():
    """
    Processes a customer payment on Razorpay Gateway:
    - Calculates MDR fee & 18% GST
    - Generates payment_id & settlement_utr
    - Inserts record into `payments` table
    - Returns Gateway ACK to merchant server
    """
    try:
        data = request.get_json(force=True) or {}
        order_id = str(data.get("order_id", ""))
        gross_amount = float(data.get("gross_amount", 0.0))
        customer_name = str(data.get("customer_name", "Customer"))
        payment_method = str(data.get("payment_method", "upi"))
        
        # Edge Case Simulation Flags
        simulate_dropped_ack = bool(data.get("simulate_dropped_ack", False))
        simulate_fee_overcharge = bool(data.get("simulate_fee_overcharge", False))

        if not order_id or gross_amount <= 0:
            return jsonify({"success": False, "error": "Invalid order_id or amount"}), 400

        # 1. Calculate Fee & GST
        # Standard: 2.00% | Overcharge Edge Case: 2.75%
        mdr_rate = 0.0275 if simulate_fee_overcharge else 0.0200
        fee = round(gross_amount * mdr_rate, 2)
        tax = round(fee * 0.18, 2)  # 18% GST on service fee
        net_credit = round(gross_amount - fee - tax, 2)

        # 2. Generate Razorpay Transaction ID & Settlement UTR
        random_suffix = "".join(random.choices("0123456789ABCDEF", k=6))
        payment_id = f"pay_{order_id.replace('ORD_', 'P')}_{random_suffix}"
        utr_num = random.randint(9823410000, 9823419999)
        settlement_utr = f"CMS{utr_num}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 3. Record in Razorpay's `payments` table in store.db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO payments (payment_id, order_id, amount, fee, tax, net_credit, settlement_utr, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'captured');
        """, (payment_id, order_id, gross_amount, fee, tax, net_credit, settlement_utr))
        conn.commit()
        conn.close()

        print(f"[RAZORPAY GATEWAY] Captured {payment_id} for {order_id} | Gross: INR {gross_amount:,.2f} | Fee: INR {fee:,.2f} | Net: INR {net_credit:,.2f} | UTR: {settlement_utr}")

        # 4. Handle Edge Case: Dropped Webhook / Missed ACK
        if simulate_dropped_ack:
            print(f"[SIMULATION] Dropped ACK for {order_id}! Gateway captured funds, but merchant received no ACK.")
            return jsonify({
                "success": False,
                "error": "Gateway Timeout / Dropped Webhook (Simulated Edge Case)",
                "payment_id": payment_id,
                "status": "captured_on_gateway_but_ack_dropped"
            }), 504

        # 5. Send Success Acknowledgment (ACK)
        return jsonify({
            "success": True,
            "ack": "PAYMENT_CAPTURED",
            "payment_id": payment_id,
            "order_id": order_id,
            "customer_name": customer_name,
            "gross_amount": gross_amount,
            "fee": fee,
            "tax": tax,
            "net_credit": net_credit,
            "settlement_utr": settlement_utr,
            "status": "captured",
            "settled_at": created_at
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/gateway/payments", methods=["GET"])
def list_gateway_payments():
    """Returns all payment transactions captured by Razorpay."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments ORDER BY rowid DESC;")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"success": True, "total_payments": len(rows), "payments": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("=================================================================")
    print(f" [GATEWAY] Razorpay Payment Gateway Server Running at: http://127.0.0.1:{PORT}")
    print(f" Gateway Database: {DB_PATH}")
    print(" Ready to process payments and send Gateway ACKs...")
    print("=================================================================")
    app.run(host="127.0.0.1", port=PORT, debug=False)
