"""
AutoReconAI - Razorpay Payment Gateway Backend Service
======================================================
Runs on port 5051 (http://127.0.0.1:5051).
Acts as the official Razorpay Payment Gateway core backend:
1. Dynamically reads `config.ini` for contracted MDR and GST rates.
2. Receives payment authorization requests from merchant checkout systems.
3. Computes MDR fee & GST (or simulates fee overcharges based on config).
4. Assigns daily settlement UTRs based on transaction dates.
5. Records captured transactions into the `payments` table in `store.db`.
6. Returns Gateway ACK to merchant server.
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

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

from config_loader import GatewayConfig

ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
DB_PATH = os.path.join(ROOT_DIR, "store.db")
PORT = 5051

app = Flask(__name__)

DAILY_UTR_CACHE = {}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/api/gateway/health", methods=["GET"])
def health_check():
    mdr = GatewayConfig.get_mdr_rate() * 100
    gst = GatewayConfig.get_gst_rate() * 100
    return jsonify({
        "status": "online",
        "service": "Razorpay Payment Gateway Core Engine",
        "port": PORT,
        "contracted_mdr": f"{mdr:.2f}%",
        "gst_rate": f"{gst:.2f}%",
        "sla_terms": GatewayConfig.get_sla_text()
    })


@app.route("/api/gateway/pay", methods=["POST"])
def process_payment():
    """
    Processes a customer payment on Razorpay Gateway:
    - Calculates MDR fee & GST dynamically from config.ini
    - Assigns realistic date & daily settlement UTR
    - Inserts record into `payments` table
    - Returns Gateway ACK to merchant server
    """
    try:
        data = request.get_json(force=True) or {}
        order_id = str(data.get("order_id", ""))
        gross_amount = float(data.get("gross_amount", 0.0))
        customer_name = str(data.get("customer_name", "Customer"))
        payment_date = str(data.get("payment_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        # Edge Case Simulation Flags
        simulate_dropped_ack = bool(data.get("simulate_dropped_ack", False))
        simulate_fee_overcharge = bool(data.get("simulate_fee_overcharge", False))

        if not order_id or gross_amount <= 0:
            return jsonify({"success": False, "error": "Invalid order_id or amount"}), 400

        # 1. Dynamically read MDR and GST from config.ini
        base_mdr = GatewayConfig.get_mdr_rate()
        gst_rate = GatewayConfig.get_gst_rate()

        # Fee calculation: Standard vs Overcharge
        mdr_rate = (base_mdr + 0.0075) if simulate_fee_overcharge else base_mdr
        fee = round(gross_amount * mdr_rate, 2)
        tax = round(fee * gst_rate, 2)
        net_credit = round(gross_amount - fee - tax, 2)

        # 2. Generate Razorpay Transaction ID & Settlement UTR
        random_suffix = "".join(random.choices("0123456789ABCDEF", k=6))
        payment_id = f"pay_{order_id.replace('ORD_', 'P')}_{random_suffix}"

        try:
            dt_obj = datetime.strptime(payment_date[:10], "%Y-%m-%d")
            date_stem = dt_obj.strftime("%Y%m%d")
            date_key = dt_obj.strftime("%Y-%m-%d")
        except Exception:
            date_stem = "20260501"
            date_key = "2026-05-01"

        if date_key not in DAILY_UTR_CACHE:
            daily_seq = random.randint(1001, 9999)
            DAILY_UTR_CACHE[date_key] = f"CMS{date_stem}{daily_seq}"

        settlement_utr = DAILY_UTR_CACHE[date_key]

        # 3. Record in Razorpay's `payments` table in store.db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                amount REAL NOT NULL,
                fee REAL NOT NULL,
                tax REAL NOT NULL,
                net_credit REAL NOT NULL,
                settlement_utr TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            INSERT INTO payments (payment_id, order_id, amount, fee, tax, net_credit, settlement_utr, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'captured');
        """, (payment_id, order_id, gross_amount, fee, tax, net_credit, settlement_utr))
        conn.commit()
        conn.close()

        print(f"[RAZORPAY GATEWAY] Captured {payment_id} for {order_id} ({payment_date[:10]}) | Gross: INR {gross_amount:,.2f} | Fee: INR {fee:,.2f} | Net: INR {net_credit:,.2f} | UTR: {settlement_utr}")

        # 4. Handle Edge Case: Dropped Webhook
        if simulate_dropped_ack:
            print(f"[SIMULATION] Dropped ACK for {order_id}! Gateway captured funds, but merchant received no ACK.")
            return jsonify({
                "success": False,
                "error": "Gateway Timeout / Dropped Webhook (Simulated Edge Case)",
                "payment_id": payment_id,
                "status": "captured_on_gateway_but_ack_dropped"
            }), 504

        # 5. Return Gateway Success ACK
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
            "settled_at": payment_date
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    print(f"==================================================")
    print(f"  ⚡ RAZORPAY PAYMENT GATEWAY CORE (PORT {PORT})")
    print(f"  Contracted SLA: {GatewayConfig.get_sla_text()}")
    print(f"==================================================")
    app.run(host="127.0.0.1", port=PORT, debug=False)
