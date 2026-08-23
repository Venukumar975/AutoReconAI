"""
FreshMart - Dedicated Backend Server & Live Cart Sync
=====================================================
1. Serves the static grocery storefront from `grocery-website/` at http://127.0.0.1:5050.
2. `POST /api/cart/add`:
   - Immediately inserts / updates the `cart` table in `store.db` (order_id = 'ACTIVE_CART').
3. `GET /api/cart`:
   - Returns the active items currently in the `cart` table.
4. `POST /api/create-order`:
   - Converts 'ACTIVE_CART' items into a real order in `orders` table (Status: PENDING).
   - Updates `cart` table with the new `order_id` (e.g. 'ORD_1001').
   - Strictly NO Razorpay API calls and NO inserts into `payments` table.
"""

import json
import os
import sqlite3
import sys
import traceback
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT_DIR, "grocery-website")
DB_PATH = os.path.join(ROOT_DIR, "store.db")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5050

app = Flask(__name__, static_folder=STATIC_DIR)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def get_db_connection():
    """Returns a SQLite connection to store.db."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.after_request
def add_header(response):
    """Disable caching so browser always receives fresh data."""
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


# 2. Live Add to Cart API (Immediately updates `cart` table in store.db)
@app.route("/api/cart/add", methods=["POST"])
def add_to_cart_db():
    """
    Inserts or increments an item in `cart` table with order_id = 'ACTIVE_CART'.
    """
    try:
        data = request.get_json(force=True) or {}
        product_name = str(data.get("product_name", ""))
        price = float(data.get("price", 0.0))

        if not product_name:
            return jsonify({"success": False, "error": "Product name is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if item already exists in ACTIVE_CART
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

        # Get total active items count
        cursor.execute("SELECT SUM(quantity) FROM cart WHERE order_id = 'ACTIVE_CART';")
        total_count = cursor.fetchone()[0] or 0

        conn.close()

        print(f"[CART DB] Added '{product_name}' (Item Qty: {current_item_qty} | Total Cart Items: {total_count})")

        return jsonify({
            "success": True,
            "product_name": product_name,
            "item_qty": current_item_qty,
            "total_cart_items": total_count
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# 3. Fetch Active Cart Items
@app.route("/api/cart", methods=["GET"])
def get_active_cart():
    """Fetches all items currently in 'ACTIVE_CART' from cart table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT product_name, quantity, total_price 
            FROM cart 
            WHERE order_id = 'ACTIVE_CART';
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        subtotal = sum(r["total_price"] for r in rows)
        total_items = sum(r["quantity"] for r in rows)

        return jsonify({
            "success": True,
            "items": rows,
            "subtotal": round(subtotal, 2),
            "total_items": total_items
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# 4. Create Order & Lock Cart Items (Status: PENDING)
@app.route("/api/create-order", methods=["POST"])
def create_order():
    """
    Finalizes the 'ACTIVE_CART' items into a real order in `orders` table.
    Updates `cart` table rows from order_id = 'ACTIVE_CART' -> order_id = 'ORD_XXXX'.
    Order status is set to PENDING.
    Does NOT touch `payments` table.
    """
    try:
        data = request.get_json(force=True) or {}
        customer_name = str(data.get("customer_name", "Priya Patel"))
        gross_amount = float(data.get("gross_amount", 0.0))

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if ACTIVE_CART has items
        cursor.execute("SELECT COUNT(*) FROM cart WHERE order_id = 'ACTIVE_CART';")
        active_items_count = cursor.fetchone()[0]

        if active_items_count == 0:
            conn.close()
            return jsonify({"success": False, "error": "Active cart is empty in database"}), 400

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
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Insert into `orders` table (Status: PENDING)
        cursor.execute("""
            INSERT INTO orders (order_id, customer_name, gross_amount, order_status, created_at)
            VALUES (?, ?, ?, 'PENDING', ?);
        """, (order_id, customer_name, gross_amount, created_at))

        # 2. Update `cart` table rows from 'ACTIVE_CART' to the new order_id
        cursor.execute("""
            UPDATE cart 
            SET order_id = ? 
            WHERE order_id = 'ACTIVE_CART';
        """, (order_id,))

        conn.commit()
        conn.close()

        print(f"[SUCCESS] Order Finalized: {order_id} | Customer: {customer_name} | Total: INR {gross_amount:,.2f} | Status: PENDING")

        return jsonify({
            "success": True,
            "order_id": order_id,
            "customer_name": customer_name,
            "gross_amount": gross_amount,
            "status": "PENDING"
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# 5. Simple Status Endpoint to View Orders in DB
@app.route("/api/orders", methods=["GET"])
def view_orders():
    """Helper to inspect all orders recorded in store.db."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders ORDER BY rowid DESC;")
        orders = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"success": True, "total_orders": len(orders), "orders": orders})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("=================================================================")
    print(f" FreshMart Backend Server Running at: http://127.0.0.1:{PORT}")
    print(f" Connected DB: {DB_PATH}")
    print(f" Serving UI: {STATIC_DIR}")
    print("=================================================================")
    app.run(host="127.0.0.1", port=PORT, debug=False)
