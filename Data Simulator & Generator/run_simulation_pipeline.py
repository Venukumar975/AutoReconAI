"""
FreshMart - End-to-End Config-Driven Simulation & Reconciliation Data Pipeline
=================================================================================
Executes the full simulation pipeline driven entirely by settings in `config.ini`:
1. Resets database (`store.db`) to clean initial catalog state.
2. Verifies backend servers (Port 5050 & Port 5051) are online.
3. Executes `auto_shopper.py` with configured count, date range, and simulation mode.
4. Executes `export_settlement_and_bank_pdf.py` to generate multi-format reconciliation datasets.

Usage:
  python "Data Simulator & Generator/run_simulation_pipeline.py"
"""

import argparse
import configparser
import os
import subprocess
import sys
import time
import urllib.request

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.ini")
OUTPUT_DIR = os.path.join(ROOT_DIR, "generated_data")
PYTHON_EXEC = sys.executable


def load_config():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    return config


def check_servers_online():
    """Verifies that both Port 5050 and Port 5051 are online."""
    print("\n[STEP 1/4] Checking Backend Services Health...")
    
    # Check FreshMart Port 5050
    try:
        urllib.request.urlopen("http://127.0.0.1:5050/api/cart", timeout=3)
        print("  [OK] FreshMart Store Backend is ONLINE (Port 5050)")
    except Exception:
        print("  [ERROR] FreshMart Store Backend (Port 5050) is offline!")
        print("  Please run in a separate terminal: python backend.py 5050")
        return False

    # Check Razorpay Port 5051
    try:
        urllib.request.urlopen("http://127.0.0.1:5051/api/gateway/health", timeout=3)
        print("  [OK] Razorpay Payment Gateway is ONLINE (Port 5051)")
    except Exception:
        print("  [ERROR] Razorpay Gateway Server (Port 5051) is offline!")
        print("  Please run: python run_razorpay_suite.py  (or python AutoReconAI/backend/gateway_server.py)")
        return False

    return True


def reset_database():
    """Cleans and re-initializes store.db."""
    print("\n[STEP 2/4] Resetting Database to Clean Initial State...")
    clean_script = os.path.join(ROOT_DIR, "database", "clean_db.py")
    init_script = os.path.join(ROOT_DIR, "database", "init_db.py")

    subprocess.run([PYTHON_EXEC, clean_script], check=True)
    subprocess.run([PYTHON_EXEC, init_script], check=True)


def run_auto_shopper():
    """Executes auto_shopper.py driven by config.ini."""
    print("\n[STEP 3/4] Launching Automated Transaction Simulator...")
    auto_shopper_script = os.path.join(CURRENT_DIR, "auto_shopper.py")
    subprocess.run([PYTHON_EXEC, auto_shopper_script], check=True)


def run_data_exporter():
    """Generates store orders CSV, settlement CSV, and configured Bank PDF/Excel statements."""
    print("\n[STEP 4/4] Exporting Reconciliation Datasets & Statement Formats...")
    exporter_script = os.path.join(CURRENT_DIR, "export_settlement_and_bank_pdf.py")
    subprocess.run([PYTHON_EXEC, exporter_script], check=True)


def main():
    config = load_config()

    sim_mode = config.get("SIMULATION", "simulation_mode", fallback="fast")
    count = config.getint("SIMULATION", "razorpay_transactions_count", fallback=55)
    start_date = config.get("SIMULATION", "start_date", fallback="2026-09-01")
    end_date = config.get("SIMULATION", "end_date", fallback="2026-09-23")
    bank_format = config.get("SIMULATION", "bank_pdf_format", fallback="UNION_BANK")

    print("=================================================================")
    print(" [PIPELINE] FreshMart Config-Driven Simulation & Data Pipeline")
    print(f" Config File: {CONFIG_PATH}")
    print(f" Target Orders: {count} Customers")
    print(f" Date Range: {start_date} to {end_date}")
    print(f" Simulation Mode: {sim_mode.upper()}")
    print(f" Bank PDF Format: {bank_format}")
    print(f" Output Folder: {OUTPUT_DIR}")
    print("=================================================================")

    if not check_servers_online():
        sys.exit(1)

    reset_database()
    run_auto_shopper()
    run_data_exporter()

    print("\n=================================================================")
    print(" [COMPLETE] All Reconciliation Datasets Successfully Generated:")
    print(f" 1. Store Orders CSV:       {os.path.join(OUTPUT_DIR, 'store_orders.csv')}")
    print(f" 2. Settlement Recon CSV:   {os.path.join(OUTPUT_DIR, 'razorpay_settlement_recon.csv')}")
    if bank_format.upper() == "UNION_BANK":
        print(f" 3. Union Bank PDF:        {os.path.join(OUTPUT_DIR, 'bank_statement_union_bank.pdf')}")
        print(f" 4. Union Bank XLSX:       {os.path.join(OUTPUT_DIR, 'bank_statement_union_bank.xlsx')}")
    else:
        print(f" 3. SBI Bank PDF:          {os.path.join(OUTPUT_DIR, 'bank_statement_sbi.pdf')}")
        print(f" 4. SBI Bank XLSX:         {os.path.join(OUTPUT_DIR, 'bank_statement_sbi.xlsx')}")
    print("=================================================================\n")


if __name__ == "__main__":
    main()
