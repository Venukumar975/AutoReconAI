import sqlite3
import os
import sys
from tabulate import tabulate  # pip install tabulate
import tkinter as tk
from tkinter import ttk

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT_DIR, "store.db")


# ---------------- Console Mode ----------------
def view_db_console():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Hide system tables like sqlite_sequence
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [t[0] for t in cursor.fetchall()]

    print("\nAvailable tables:")
    for i, t in enumerate(tables, 1):
        print(f"{i}. {t}")

    choice = int(input("\nChoose a table number: "))
    table_name = tables[choice - 1]

    cursor.execute(f"SELECT * FROM {table_name};")
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]

    print(f"\n📊 Records in {table_name}:")
    print(tabulate(rows, headers=col_names, tablefmt="grid"))

    conn.close()


# ---------------- GUI Mode ----------------
def show_table(table_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name};")
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]
    conn.close()

    popup = tk.Toplevel()
    popup.title(f"Records in {table_name}")

    tree = ttk.Treeview(popup, columns=col_names, show="headings")
    for col in col_names:
        tree.heading(col, text=col)
        tree.column(col, width=120)
    for row in rows:
        tree.insert("", "end", values=row)
    tree.pack(expand=True, fill="both")


def view_db_gui():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Hide system tables here too
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [t[0] for t in cursor.fetchall()]
    conn.close()

    root = tk.Tk()
    root.title("SQLite Table Viewer")

    label = tk.Label(root, text="Choose a table to view:", font=("Arial", 12))
    label.pack(pady=10)

    for t in tables:
        btn = tk.Button(root, text=t, command=lambda tn=t: show_table(tn))
        btn.pack(fill="x", padx=20, pady=5)

    root.mainloop()


# ---------------- Entry Point ----------------
if __name__ == "__main__":
    if "--console" in sys.argv:
        view_db_console()
    elif "--interface" in sys.argv:
        view_db_gui()
    else:
        print("Usage:")
        print("  python database/view.py --console   # show tables in console")
        print("  python database/view.py --interface # show tables in popup GUI")
