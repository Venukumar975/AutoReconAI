"""
Edge Case Simulator 1: Dropped Webhooks (State Desync)
=====================================================
Simulates dropped webhooks by picking N randomly captured orders
and updating their store order status to 'PENDING'.
"""

import sqlite3

def apply_dropped_webhooks_simulation(db_path, dropped_count):
    if dropped_count <= 0:
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT order_id FROM orders WHERE order_status = 'FULFILLED' ORDER BY RANDOM() LIMIT ?;", (dropped_count,))
    target_orders = [r["order_id"] for r in cursor.fetchall()]

    for oid in target_orders:
        cursor.execute("UPDATE orders SET order_status = 'PENDING' WHERE order_id = ?;", (oid,))

    conn.commit()
    conn.close()

    print(f"[EDGE CASE 1] Dropped Webhooks: Set {len(target_orders)} orders ({', '.join(target_orders)}) to PENDING.")
    return target_orders
