"""
FreshMart - Config-Driven Automated Transaction Simulator
==========================================================
Execution Modes:
1. `normal`: Playwright Visual Chromium Browser with realistic human delays (250ms click, 450ms modal, 80ms slow_mo).
2. `fast`: Playwright Visual Chromium Browser with fast-forwarded UI delays (80ms click, 150ms modal, 30ms slow_mo).
3. `super_fast`: Pure Python HTTP API Requests (NO Playwright). Executes 500+ transactions in seconds!
"""

import argparse
import configparser
import json
import os
import random
import sys
import time
import urllib.request
from datetime import datetime, timedelta

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.ini")
PRODUCTS_JSON_PATH = os.path.join(ROOT_DIR, "products.json")

# 55 Realistic Indian Customer Profiles
CUSTOMERS = [
    "Priya Patel", "Rahul Verma", "Sneha Iyer", "Aarav Sharma", "Meera Kumar",
    "Vikram Reddy", "Ananya Joshi", "Rohan Mehta", "Kavita Nair", "Siddharth Rao",
    "Deepa Menon", "Arjun Kapoor", "Pooja Deshmukh", "Manish Singhania", "Shreya Roy",
    "Aditya Sengupta", "Neha Agarwal", "Varun Chopra", "Ritu Kulkarni", "Nikhil Nair",
    "Tanvi Hegde", "Harish Pandey", "Rashi Bansal", "Gautam Trivedi", "Divya Saxena",
    "Kunal Malhotra", "Isha Bhatt", "Abhishek Tiwari", "Radhika Sen", "Pranav Kulkarni",
    "Suman Ghosh", "Nandini Das", "Sanjay Nambiar", "Aparna Pillai", "Devendra Jha",
    "Tarun Mathur", "Bhavna Mishra", "Sameer Qureshi", "Shalini Kaul", "Rajesh Pillai",
    "Ankita Mukherjee", "Vivek Sundaram", "Leela Krishnan", "Mohit Chawla", "Preeti Mahajan",
    "Suresh Prabhu", "Deepali Gokhale", "Alok Srivastava", "Kiran Varma", "Sunil Chettri",
    "Geeta Swaminathan", "Ashwin Murthy", "Pallavi Rane", "Chetan Bhagat", "Zoya Farooqui"
]

def load_config():
    """Reads configuration from config.ini."""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    return config


def load_products():
    """Reads product items directly from root products.json."""
    if os.path.exists(PRODUCTS_JSON_PATH):
        with open(PRODUCTS_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(f"Root product catalog not found at: {PRODUCTS_JSON_PATH}")


def generate_order_date(index, total_count, start_str, end_str):
    """Generates realistic dates distributed strictly between start_date and end_date."""
    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_str, "%Y-%m-%d")
    except Exception:
        start_dt = datetime(2026, 9, 1)
        end_dt = datetime(2026, 9, 23)

    day_span = max((end_dt - start_dt).days, 1)
    base_offset = int((index - 1) * (day_span / max(total_count - 1, 1)))
    offset = max(0, min(day_span, base_offset + random.randint(-1, 1)))

    target_dt = start_dt + timedelta(days=offset)
    hour = random.randint(9, 21)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)

    return target_dt.strftime(f"%Y-%m-%d {hour:02d}:{minute:02d}:{second:02d}")


def run_super_fast_requests(count, start_date, end_date):
    """
    SUPER_FAST MODE: Direct Python HTTP API Requests (NO Playwright).
    Executes transactions lightning-fast directly against server endpoints!
    """
    print("=================================================================")
    print(" [SUPER_FAST MODE] Direct HTTP API Transaction Simulator")
    print(f" Target Orders: {count} Customers")
    print(f" Configured Date Range: {start_date} to {end_date}")
    print(" Mode: DIRECT HTTP REQUESTS (No Playwright browser overhead)")
    print("=================================================================\n")

    products = load_products()
    start_time = time.time()

    for idx in range(1, count + 1):
        customer_name = CUSTOMERS[(idx - 1) % len(CUSTOMERS)]
        order_date = generate_order_date(idx, count, start_date, end_date)
        date_short = order_date[:10]

        items_to_buy = random.sample(products, k=random.randint(1, min(4, len(products))))

        # 1. Add items to cart via POST /api/cart/add
        for item in items_to_buy:
            qty = random.randint(1, 2)
            for _ in range(qty):
                req_data = json.dumps({"product_name": item["name"], "price": item["price"]}).encode("utf-8")
                req = urllib.request.Request(
                    "http://127.0.0.1:5050/api/cart/add",
                    data=req_data,
                    headers={"Content-Type": "application/json"}
                )
                urllib.request.urlopen(req)

        # 2. Complete order checkout via POST /api/create-order
        order_req_data = json.dumps({
            "customer_name": customer_name,
            "created_at": order_date
        }).encode("utf-8")

        order_req = urllib.request.Request(
            "http://127.0.0.1:5050/api/create-order",
            data=order_req_data,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(order_req)
        result = json.loads(resp.read().decode("utf-8"))

        if result.get("success"):
            print(f"[{idx:02d}/{count}] Date: {date_short} | Customer: {customer_name:<18} | Order: {result.get('order_id')} | Gross Total: INR {result.get('gross_amount'):,.2f} [OK]")

    elapsed = time.time() - start_time
    print("\n=================================================================")
    print(f" [DONE] Successfully Executed All {count} Transactions in {elapsed:.2f}s!")
    print(" All orders & gateway payouts stored in store.db!")
    print("=================================================================\n")


def run_playwright_auto_shopper(count, start_date, end_date, is_fast_mode):
    """
    NORMAL / FAST MODE: Visual Playwright Chromium Browser Simulator.
    Drives a real visible browser window to showcase UI shopping interactions.
    """
    from playwright.sync_api import sync_playwright

    click_delay = 80 if is_fast_mode else 250
    modal_delay = 150 if is_fast_mode else 450
    slow_mo_val = 30 if is_fast_mode else 80

    mode_name = "FAST" if is_fast_mode else "NORMAL"

    print("=================================================================")
    print(f" [{mode_name} MODE] Playwright Visual Browser Simulator")
    print(f" Target Orders: {count} Customers")
    print(f" Configured Date Range: {start_date} to {end_date}")
    print(f" Mode: VISUAL BROWSER (Click Delay: {click_delay}ms, SlowMo: {slow_mo_val}ms)")
    print("=================================================================\n")

    products = load_products()
    product_names = [p["name"] for p in products]

    with sync_playwright() as p:
        print("[BROWSER] Launching Chromium Browser (Visible UI)...")
        browser = p.chromium.launch(headless=False, slow_mo=slow_mo_val)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        page.on("dialog", lambda dialog: dialog.accept())

        print("[NAVIGATE] Loading http://127.0.0.1:5050 ...")
        page.goto("http://127.0.0.1:5050")
        page.wait_for_load_state("networkidle")
        time.sleep(0.5)

        print("\n--- Running Automated Customer Orders ---\n")

        for idx in range(1, count + 1):
            customer_name = CUSTOMERS[(idx - 1) % len(CUSTOMERS)]
            order_date = generate_order_date(idx, count, start_date, end_date)
            date_short = order_date[:10]

            items_to_buy = random.sample(product_names, k=random.randint(1, min(4, len(product_names))))
            print(f"[{idx:02d}/{count}] Date: {date_short} | Customer: {customer_name:<18} | Items: {len(items_to_buy)} ...")

            for item_name in items_to_buy:
                qty = random.randint(1, 2)
                for _ in range(qty):
                    card = page.locator(f".product-card:has-text('{item_name}')")
                    if card.count() > 0:
                        card.locator(".btn-add-cart").click()
                        if click_delay > 0:
                            time.sleep(click_delay / 1000)

            if modal_delay > 0:
                time.sleep(modal_delay / 1000)

            page.locator(".cart-btn").click()

            if modal_delay > 0:
                time.sleep(modal_delay / 1000)

            page.evaluate(f"window.CURRENT_SIM_CUSTOMER = '{customer_name}'")
            page.evaluate(f"window.CURRENT_SIM_DATE = '{order_date}'")

            buy_btn = page.locator("#btn-cart-buy")
            if buy_btn.is_enabled():
                with page.expect_response("**/api/create-order", timeout=5000):
                    buy_btn.click()

            time.sleep(0.2)

            try:
                latest_order_resp = page.request.get("http://127.0.0.1:5050/api/orders")
                orders_data = latest_order_resp.json()
                if orders_data.get("orders"):
                    latest = orders_data["orders"][0]
                    print(f"       [SUCCESS] {latest['order_id']} ({date_short}) | Total: INR {latest['gross_amount']:,.2f} | Status: {latest['order_status']}")
            except Exception:
                pass

        print("\n=================================================================")
        print(f" [DONE] Successfully Completed All {count} Transactions!")
        print("=================================================================")
        time.sleep(1)
        browser.close()


def main(target_count=None, mode=None):
    config = load_config()

    sim_mode = (mode or config.get("SIMULATION", "simulation_mode", fallback="super_fast")).lower()
    count = target_count or config.getint("SIMULATION", "razorpay_transactions_count", fallback=55)
    start_date = config.get("SIMULATION", "start_date", fallback="2026-09-01")
    end_date = config.get("SIMULATION", "end_date", fallback="2026-09-23")

    if sim_mode == "super_fast":
        # Pure Python HTTP API Requests (Fastest)
        run_super_fast_requests(count, start_date, end_date)
    elif sim_mode == "fast":
        # Playwright Visible Browser (Fast-Forwarded UI)
        run_playwright_auto_shopper(count, start_date, end_date, is_fast_mode=True)
    else:
        # Playwright Visible Browser (Normal Human Speed)
        run_playwright_auto_shopper(count, start_date, end_date, is_fast_mode=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FreshMart Automated Transaction Simulator")
    parser.add_argument("--count", type=int, help="Override transaction count")
    parser.add_argument("--mode", type=str, choices=["normal", "fast", "super_fast"], help="Override simulation mode")
    args = parser.parse_args()

    main(target_count=args.count, mode=args.mode)
