"""
Database Cleanup Script
=======================
Deletes / drops all tables from `store.db`.
If tables do not exist, notifies the user with a simple message.
"""

import os
import sqlite3

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT_DIR, "store.db")

TARGET_TABLES = ["cart", "payments", "orders", "products"]


def clean_db():
    """Drops tables from store.db. Notifies user if tables do not exist."""
    if not os.path.exists(DB_PATH):
        print(f"[INFO] Database file 'store.db' does not exist.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check which tables currently exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]

    if not existing_tables:
        print("[INFO] No tables found in database to delete.")
        conn.close()
        return

    # Delete / Drop tables
    deleted = []
    for table in TARGET_TABLES:
        if table in existing_tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table};")
            deleted.append(table)

    conn.commit()
    conn.close()

    print(f"[SUCCESS] Deleted tables: {', '.join(deleted)} from store.db")


if __name__ == "__main__":
    clean_db()
