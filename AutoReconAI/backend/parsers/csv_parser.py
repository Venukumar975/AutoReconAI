"""
AutoReconAI - CSV Parsers for Orders & Settlement Ledgers
=========================================================
Parses:
1. `store_orders.csv`
2. `razorpay_settlement_recon.csv`
"""

import csv
from typing import Dict, List, Any


def parse_orders_csv(file_path: str) -> List[Dict[str, Any]]:
    """Parses store_orders.csv into structured dictionaries."""
    orders = []
    with open(file_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                gross = float(row.get("gross_amount", 0.0))
            except ValueError:
                gross = 0.0

            orders.append({
                "order_id": row.get("order_id", "").strip(),
                "customer_name": row.get("customer_name", "").strip(),
                "gross_amount": gross,
                "order_status": row.get("order_status", "").strip(),
                "created_at": row.get("created_at", "").strip()
            })
    return orders


def parse_settlement_csv(file_path: str) -> List[Dict[str, Any]]:
    """Parses razorpay_settlement_recon.csv into structured dictionaries."""
    settlements = []
    with open(file_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                amount = float(row.get("amount", 0.0))
                fee = float(row.get("fee", 0.0))
                tax = float(row.get("tax", 0.0))
                net_credit = float(row.get("net_credit", 0.0))
            except ValueError:
                amount = fee = tax = net_credit = 0.0

            settlements.append({
                "settlement_id": row.get("settlement_id", "").strip(),
                "settlement_utr": row.get("settlement_utr", "").strip(),
                "payment_id": row.get("payment_id", "").strip(),
                "order_id": row.get("order_id", "").strip(),
                "amount": amount,
                "fee": fee,
                "tax": tax,
                "net_credit": net_credit,
                "type": row.get("type", "payment").strip(),
                "status": row.get("status", "captured").strip(),
                "created_at": row.get("created_at", "").strip(),
                "settled_at": row.get("settled_at", "").strip()
            })
    return settlements
