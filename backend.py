"""
FreshMart - Storefront Backend & Order Processor
=================================================
Runs on port 5050 (http://127.0.0.1:5050).
1. Serves the static grocery storefront from `grocery-website/`.
2. `POST /api/cart/add` & `GET /api/cart`: Live active cart management.
3. `POST /api/create-order`:
   - Step A: Calculates exact Grand Total = Subtotal + 5% GST Tax + Delivery Fee.
   - Step B: Creates the order in `orders` table (Status: PENDING) with custom/real-time date.
   - Step C: Links active cart items to `order_id` in `cart` table.
   - Step D: Sends payment authorization request to Razorpay Gateway (Port 5051).
   - Step E:
     - If Gateway returns Success ACK -> Updates `orders` table to FULFILLED.
     - If Gateway ACK is missed / dropped -> Order remains in PENDING (Edge Case).
"""

import json
import os
import sqlite3
import sys
import traceback
import urllib.request
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT_DIR, "grocery-website")
DB_PATH = os.path.join(ROOT_DIR, "store.db")
PRODUCTS_JSON_PATH = os.path.join(ROOT_DIR, "products.json")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
RAZORPAY_GATEWAY_URL = "http://127.0.0.1:5051/api/gateway/pay"

app = Flask(__name__, static_folder=STATIC_DIR)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def ensure_db_schema():
    """Ensures that the 4 lean tables exist in store.db."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            gross_amount REAL NOT NULL,
            order_status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            amount REAL NOT NULL,
            fee REAL NOT NULL,
            tax REAL NOT NULL,
            net_credit REAL NOT NULL,
            settlement_utr TEXT NOT NULL,
            status TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def get_db():
    ensure_db_schema()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# 1. Frontend Static Routes
@app.route("/")
def serve_home():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(STATIC_DIR, path)


# 2. Live Add to Cart API
@app.route("/api/cart/add", methods=["POST"])
def add_to_cart_db():
    try:
        data = request.get_json(force=True) or {}
        product_name = str(data.get("product_name", ""))
        price = float(data.get("price", 0.0))

        if not product_name:
            return jsonify({"success": False, "error": "Product name is required"}), 400

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, quantity FROM cart 
            WHERE order_id = 'ACTIVE_CART' AND product_name = ?;
        """, (product_name,))
        existing = cursor.fetchone()

        if existing:
            new_qty = existing["quantity"] + 1
            new_total = round(new_qty * price, 2)
            cursor.execute("""
                UPDATE cart 
                SET quantity = ?, total_price = ? 
                WHERE id = ?;
            """, (new_qty, new_total, existing["id"]))
            current_item_qty = new_qty
        else:
            cursor.execute("""
                INSERT INTO cart (order_id, product_name, quantity, total_price)
                VALUES ('ACTIVE_CART', ?, 1, ?);
            """, (product_name, price))
            current_item_qty = 1

        conn.commit()

        cursor.execute("SELECT SUM(quantity) FROM cart WHERE order_id = 'ACTIVE_CART';")
        total_count = cursor.fetchone()[0] or 0
        conn.close()

        return jsonify({
            "success": True,
            "product_name": product_name,
            "item_qty": current_item_qty,
            "total_cart_items": total_count
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# 3. Fetch Active Cart Items with Bill Breakdown
@app.route("/api/cart", methods=["GET"])
def get_active_cart():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT product_name, quantity, total_price 
            FROM cart 
            WHERE order_id = 'ACTIVE_CART';
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        subtotal = round(sum(r["total_price"] for r in rows), 2)
        total_items = sum(r["quantity"] for r in rows)

        if subtotal > 0:
            gst_tax = round(subtotal * 0.05, 2)  # 5% GST on groceries
            delivery_fee = 0.00 if subtotal >= 499.0 else 40.00
            grand_total = round(subtotal + gst_tax + delivery_fee, 2)
        else:
            gst_tax = 0.00
            delivery_fee = 0.00
            grand_total = 0.00

        return jsonify({
            "success": True,
            "items": rows,
            "subtotal": subtotal,
            "gst_tax": gst_tax,
            "delivery_fee": delivery_fee,
            "grand_total": grand_total,
            "total_items": total_items
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# 4. Create Order & Process with Razorpay Gateway
@app.route("/api/create-order", methods=["POST"])
def create_order():
    try:
        data = request.get_json(force=True) or {}
        customer_name = str(data.get("customer_name", "Priya Patel"))
        custom_date = data.get("created_at") or data.get("order_date")
        simulate_dropped_ack = bool(data.get("simulate_dropped_ack", False))
        simulate_fee_overcharge = bool(data.get("simulate_fee_overcharge", False))

        conn = get_db()
        cursor = conn.cursor()

        # Fetch active cart items and compute bill
        cursor.execute("SELECT total_price FROM cart WHERE order_id = 'ACTIVE_CART';")
        active_rows = cursor.fetchall()
        if not active_rows:
            conn.close()
            return jsonify({"success": False, "error": "Active cart is empty in database"}), 400

        subtotal = round(sum(r[0] for r in active_rows), 2)
        gst_tax = round(subtotal * 0.05, 2)  # 5% GST on grocery items
        delivery_fee = 0.00 if subtotal >= 499.0 else 40.00
        gross_grand_total = round(subtotal + gst_tax + delivery_fee, 2)

        # Generate next safe unique order_id
        cursor.execute("SELECT order_id FROM orders;")
        existing_rows = cursor.fetchall()
        max_num = 1000
        for row in existing_rows:
            oid = str(row[0])
            if oid.startswith("ORD_"):
                try:
                    num = int(oid.replace("ORD_", ""))
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass

        order_id = f"ORD_{max_num + 1}"
        created_at = custom_date if custom_date else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Step A: Insert into `orders` table (Gross Amount = Grand Total with Tax + Delivery)
        cursor.execute("""
            INSERT INTO orders (order_id, customer_name, gross_amount, order_status, created_at)
            VALUES (?, ?, ?, 'PENDING', ?);
        """, (order_id, customer_name, gross_grand_total, created_at))

        # Step B: Link cart items to this order_id
        cursor.execute("""
            UPDATE cart 
            SET order_id = ? 
            WHERE order_id = 'ACTIVE_CART';
        """, (order_id,))
        conn.commit()

        print(f"[STORE DB] Order Created: {order_id} ({created_at[:10]}) | Total: INR {gross_grand_total:,.2f} | Status: PENDING")

        # Step C: Send Grand Total & Date to Razorpay Gateway (Port 5051)
        gateway_payload = {
            "order_id": order_id,
            "gross_amount": gross_grand_total,
            "customer_name": customer_name,
            "payment_date": created_at,
            "simulate_dropped_ack": simulate_dropped_ack,
            "simulate_fee_overcharge": simulate_fee_overcharge
        }

        gateway_ack = None
        try:
            req = urllib.request.Request(
                RAZORPAY_GATEWAY_URL,
                data=json.dumps(gateway_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                gateway_ack = json.loads(resp.read().decode("utf-8"))
        except Exception as gw_err:
            print(f"[GATEWAY WARNING] Gateway communication error/dropped ACK: {gw_err}")

        # Step D: Check Gateway Acknowledgment
        if gateway_ack and gateway_ack.get("success"):
            cursor.execute("""
                UPDATE orders 
                SET order_status = 'FULFILLED' 
                WHERE order_id = ?;
            """, (order_id,))
            conn.commit()
            final_status = "FULFILLED"
            payment_id = gateway_ack.get("payment_id")
            print(f"[SUCCESS] Gateway ACK Received! {order_id} FULFILLED ({payment_id})")
        else:
            final_status = "PENDING"
            payment_id = None
            print(f"[WARNING] No ACK received for {order_id}. Order remains PENDING!")

        conn.close()

        return jsonify({
            "success": True,
            "order_id": order_id,
            "customer_name": customer_name,
            "subtotal": subtotal,
            "gst_tax": gst_tax,
            "delivery_fee": delivery_fee,
            "gross_amount": gross_grand_total,
            "order_status": final_status,
            "payment_id": payment_id,
            "created_at": created_at,
            "gateway_ack": gateway_ack
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# 5. Helper to view orders
@app.route("/api/orders", methods=["GET"])
def view_orders():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders ORDER BY rowid DESC;")
        orders = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"success": True, "total_orders": len(orders), "orders": orders})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    ensure_db_schema()
    print("=================================================================")
    print(f" FreshMart Storefront Server Running at: http://127.0.0.1:{PORT}")
    print(f" Connected DB: {DB_PATH}")
    print(f" Razorpay Gateway Target: {RAZORPAY_GATEWAY_URL}")
    print("=================================================================")
    app.run(host="127.0.0.1", port=PORT, debug=False)
