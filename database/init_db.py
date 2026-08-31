"""
Database Schema & Initialization
================================
Initializes the 4 lean tables in SQLite `store.db`:
1. products  - Loaded from isolated `products.json`
2. orders    - Store sale bill record
3. cart      - Item line breakdown per order
4. payments  - Gateway fees, GST & bank UTR ledger
"""

import json
import os
import sqlite3

# Point to root directory store.db and products.json
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT_DIR, "store.db")
CATALOG_PATH = os.path.join(ROOT_DIR, "products.json")


def init_db():
    """Initializes the 4 tables in store.db and seeds products from products.json."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. products table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL
        );
    """)

    # 2. orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            gross_amount REAL NOT NULL,
            order_status TEXT NOT NULL DEFAULT 'FULFILLED',
            created_at TEXT NOT NULL
        );
    """)

    # 3. cart table (individual line items for each order)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
    """)

    # 4. payments table (gateway transaction & fee audit)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            amount REAL NOT NULL,
            fee REAL NOT NULL,
            tax REAL NOT NULL,
            tds REAL DEFAULT 0.0,
            net_credit REAL NOT NULL,
            settlement_utr TEXT,
            status TEXT NOT NULL DEFAULT 'captured',
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
    """)

    # Load and seed products from isolated products.json
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        for p in catalog:
            cursor.execute("""
                INSERT OR REPLACE INTO products (id, name, price)
                VALUES (?, ?, ?);
            """, (p["id"], p["name"], p["price"]))

    conn.commit()
    conn.close()
    print("[SUCCESS] Initialized store.db with 4 tables from products.json.")


if __name__ == "__main__":
    init_db()
