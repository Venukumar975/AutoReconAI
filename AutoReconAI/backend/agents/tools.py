import os
import re
import sqlite3
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from config_loader import GatewayConfig

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
STORE_DB_PATH = os.path.join(ROOT_DIR, "store.db")


class ReconToolbox:

    @staticmethod
    def get_reconciliation_overview(session_data):
        orders = session_data.get("orders", [])
        settlements = session_data.get("settlements", [])
        bank_txns = session_data.get("bank_txns", [])

        if not orders or not settlements:
            return {
                "status": "NO_SESSION_DATA",
                "message": "No active reconciliation data loaded. Please ensure Store Orders CSV and Settlement CSV are uploaded."
            }

        orders_by_id = {o["order_id"]: o for o in orders}

        total_settlement_txns = len(settlements)
        total_store_orders = len(orders)
        total_gmv = sum(float(s.get("amount", 0.0)) for s in settlements)
        total_fees = sum(float(s.get("fee", 0.0)) for s in settlements)
        total_gst = sum(float(s.get("tax", 0.0)) for s in settlements)
        total_bank_deposited = sum(float(b.get("credit", 0.0)) for b in bank_txns if b.get("is_gateway_credit"))

        mdr_threshold = GatewayConfig.get_mdr_rate() + 0.0005

        dropped_webhooks = []
        fee_overcharges = []
        orphan_refunds = []

        for s in settlements:
            oid = s["order_id"]
            amount = float(s.get("amount", 0.0))
            fee = float(s.get("fee", 0.0))
            net_credit = float(s.get("net_credit", 0.0))
            order_info = orders_by_id.get(oid)

            # Dropped webhook
            if order_info and order_info.get("order_status") == "PENDING":
                dropped_webhooks.append(oid)

            # MDR fee overcharge against dynamic config
            fee_rate = (fee / amount) if amount > 0 else 0.0
            if fee_rate > mdr_threshold:
                fee_overcharges.append(oid)

            # Orphan customer refund (Prior-period return deductions)
            if oid not in orders_by_id or net_credit < 0:
                orphan_refunds.append(oid)

        unique_mismatched = sorted(list(set(dropped_webhooks + fee_overcharges + orphan_refunds)))
        mismatched_count = len(unique_mismatched)
        matched_count = max(0, total_settlement_txns - mismatched_count)
        match_rate = round((matched_count / max(total_settlement_txns, 1)) * 100, 1)

        return {
            "total_settlement_transactions": total_settlement_txns,
            "total_store_orders": total_store_orders,
            "total_gmv_inr": round(total_gmv, 2),
            "total_gateway_fees_inr": round(total_fees, 2),
            "total_gst_inr": round(total_gst, 2),
            "total_bank_deposited_inr": round(total_bank_deposited, 2),
            "match_rate": f"{match_rate}%",
            "matched_transactions_count": matched_count,
            "mismatched_transactions_count": mismatched_count,
            "contracted_sla_terms": GatewayConfig.get_sla_text(),
            "mismatch_categories": {
                "dropped_webhooks": {
                    "count": len(set(dropped_webhooks)),
                    "order_ids": sorted(list(set(dropped_webhooks)))
                },
                "fee_overcharges": {
                    "count": len(set(fee_overcharges)),
                    "order_ids": sorted(list(set(fee_overcharges)))
                },
                "orphan_refunds": {
                    "count": len(set(orphan_refunds)),
                    "order_ids": sorted(list(set(orphan_refunds))),
                    "note": "Includes prior-period customer return deductions"
                }
            }
        }

    @staticmethod
    def list_mismatches(session_data, category="all"):
        orders = session_data.get("orders", [])
        settlements = session_data.get("settlements", [])
        bank_txns = session_data.get("bank_txns", [])

        orders_by_id = {o["order_id"]: o for o in orders}
        bank_by_utr = {b["extracted_utr"]: b for b in bank_txns if b.get("extracted_utr") and b["extracted_utr"] != "-"}

        mdr_threshold = GatewayConfig.get_mdr_rate() + 0.0005
        contracted_mdr = GatewayConfig.get_mdr_rate()
        gst_rate = GatewayConfig.get_gst_rate()

        results = []
        category_lower = (category or "all").lower()

        for s in settlements:
            oid = s["order_id"]
            amount = float(s.get("amount", 0.0))
            fee = float(s.get("fee", 0.0))
            tax = float(s.get("tax", 0.0))
            net_credit = float(s.get("net_credit", 0.0))
            utr = s.get("settlement_utr", "-")

            order_info = orders_by_id.get(oid)
            order_status = order_info.get("order_status") if order_info else "UNKNOWN"

            fee_rate = (fee / amount) if amount > 0 else 0.0
            is_overcharged = fee_rate > mdr_threshold
            is_dropped_webhook = (order_status == "PENDING")
            is_orphan_refund = (oid not in orders_by_id or net_credit < 0)

            bank_info = bank_by_utr.get(utr)
            is_missing_bank_credit = (bank_info is None)

            anomalies = []
            overcharge_amt = 0.0

            if is_overcharged:
                expected_fee = amount * contracted_mdr
                expected_tax = expected_fee * gst_rate
                overcharge_amt = (fee + tax) - (expected_fee + expected_tax)
                anomalies.append({
                    "type": "FEE_OVERCHARGE",
                    "severity": "HIGH",
                    "issue": f"MDR Rate billed at {fee_rate*100:.2f}% vs contracted {contracted_mdr*100:.2f}% SLA",
                    "claimable_amount": round(overcharge_amt, 2),
                    "action_required": "File Razorpay merchant dispute ticket"
                })

            if is_dropped_webhook:
                anomalies.append({
                    "type": "DROPPED_WEBHOOK",
                    "severity": "MEDIUM",
                    "issue": "Store order status is PENDING, but gateway captured payment and settled funds to bank",
                    "claimable_amount": 0.0,
                    "action_required": "Update order to FULFILLED manually in store dashboard"
                })

            if is_orphan_refund:
                anomalies.append({
                    "type": "ORPHAN_CUSTOMER_REFUND",
                    "severity": "LOW",
                    "issue": "Settlement contains prior-period customer return refund deduction",
                    "claimable_amount": 0.0,
                    "action_required": "Post internal accounting adjustment to Prior-Period Returns ledger"
                })

            if is_missing_bank_credit:
                anomalies.append({
                    "type": "MISSING_BANK_CREDIT",
                    "severity": "CRITICAL",
                    "issue": f"No bank deposit found matching UTR: {utr}",
                    "claimable_amount": round(net_credit, 2),
                    "action_required": "Contact nodal bank for unsettled UTR trace"
                })

            if anomalies:
                if category_lower == "all" or any(category_lower in a["type"].lower() for a in anomalies):
                    results.append({
                        "order_id": oid,
                        "payment_id": s.get("payment_id", "-"),
                        "settlement_utr": utr,
                        "billed_amount": amount,
                        "charged_fee": fee,
                        "charged_tax": tax,
                        "net_credit": net_credit,
                        "store_status": order_status,
                        "anomalies": anomalies
                    })

        return {
            "total_mismatched_orders": len(results),
            "filter_applied": category,
            "mismatches": results
        }

    @staticmethod
    def inspect_order_lifecycle(session_data, order_id):
        orders = session_data.get("orders", [])
        settlements = session_data.get("settlements", [])
        bank_txns = session_data.get("bank_txns", [])

        clean_oid = str(order_id).strip().upper()
        if not clean_oid.startswith("ORD_") and clean_oid.isdigit():
            clean_oid = f"ORD_{clean_oid}"

        order_record = next((o for o in orders if o.get("order_id") == clean_oid), None)
        settlement_record = next((s for s in settlements if s.get("order_id") == clean_oid), None)

        matched_utr = settlement_record.get("settlement_utr") if settlement_record else None
        bank_record = next((b for b in bank_txns if b.get("extracted_utr") == matched_utr and matched_utr != "-"), None) if matched_utr else None

        actual_fee_rate = 0.0
        overcharge_amount = 0.0
        contracted_mdr = GatewayConfig.get_mdr_rate()
        gst_rate = GatewayConfig.get_gst_rate()
        mdr_threshold = contracted_mdr + 0.0005

        if settlement_record:
            amt = float(settlement_record.get("amount", 0.0))
            fee = float(settlement_record.get("fee", 0.0))
            tax = float(settlement_record.get("tax", 0.0))
            if amt > 0:
                actual_fee_rate = (fee / amt) * 100.0
                if actual_fee_rate > (mdr_threshold * 100.0):
                    expected_fee = amt * contracted_mdr
                    expected_tax = expected_fee * gst_rate
                    overcharge_amount = (fee + tax) - (expected_fee + expected_tax)

        return {
            "order_id": clean_oid,
            "store_order_ledger": {
                "present": bool(order_record),
                "customer_name": order_record.get("customer_name") if order_record else "N/A",
                "gross_amount": order_record.get("gross_amount", 0.0) if order_record else 0.0,
                "order_status": order_record.get("order_status") if order_record else "NOT_FOUND",
                "created_at": order_record.get("created_at") if order_record else "N/A"
            },
            "razorpay_settlement_ledger": {
                "present": bool(settlement_record),
                "payment_id": settlement_record.get("payment_id") if settlement_record else "N/A",
                "billed_amount": settlement_record.get("amount", 0.0) if settlement_record else 0.0,
                "fee_charged": settlement_record.get("fee", 0.0) if settlement_record else 0.0,
                "tax_charged": settlement_record.get("tax", 0.0) if settlement_record else 0.0,
                "effective_fee_rate": f"{actual_fee_rate:.2f}%",
                "net_credit": settlement_record.get("net_credit", 0.0) if settlement_record else 0.0,
                "settlement_utr": matched_utr if matched_utr else "N/A"
            },
            "bank_statement_ledger": {
                "present": bool(bank_record),
                "deposit_amount": bank_record.get("credit", 0.0) if bank_record else 0.0,
                "deposit_date": bank_record.get("txn_date") if bank_record else "N/A",
                "narration": bank_record.get("primary_narration") if bank_record else "N/A",
                "matched_utr": bank_record.get("extracted_utr") if bank_record else "N/A"
            },
            "financial_audit_diagnosis": {
                "is_dropped_webhook": bool(order_record and order_record.get("order_status") == "PENDING" and settlement_record),
                "is_fee_overcharge": actual_fee_rate > (mdr_threshold * 100.0),
                "contracted_sla_rate": GatewayConfig.get_sla_text(),
                "overcharge_amount_inr": round(overcharge_amount, 2),
                "recommended_action": (
                    "Fulfill order manually in store (Dropped Webhook). No Razorpay dispute needed."
                    if (order_record and order_record.get("order_status") == "PENDING")
                    else (
                        f"Submit dispute claim to Razorpay for ₹{round(overcharge_amount, 2)} MDR overcharge."
                        if actual_fee_rate > (mdr_threshold * 100.0)
                        else "Transaction reconciled 100% cleanly across all 3 ledgers."
                    )
                )
            }
        }

    @staticmethod
    def calculate_fee_discrepancies(session_data):
        settlements = session_data.get("settlements", [])
        if not settlements:
            return {"status": "NO_DATA", "message": "No settlement data available."}

        overcharged_list = []
        total_overcharge = 0.0
        contracted_mdr = GatewayConfig.get_mdr_rate()
        gst_rate = GatewayConfig.get_gst_rate()
        mdr_threshold = contracted_mdr + 0.0005

        for s in settlements:
            oid = s["order_id"]
            amount = float(s.get("amount", 0.0))
            fee = float(s.get("fee", 0.0))
            tax = float(s.get("tax", 0.0))
            rate = (fee / amount) if amount > 0 else 0.0

            if rate > mdr_threshold:
                expected_fee = amount * contracted_mdr
                expected_tax = expected_fee * gst_rate
                overcharge = (fee + tax) - (expected_fee + expected_tax)
                if overcharge > 0:
                    total_overcharge += overcharge
                    overcharged_list.append({
                        "order_id": oid,
                        "payment_id": s.get("payment_id", "-"),
                        "settlement_utr": s.get("settlement_utr", "-"),
                        "billed_amount": amount,
                        "charged_fee": fee,
                        "charged_tax": tax,
                        "effective_charged_rate": f"{rate*100:.2f}%",
                        "contracted_fee": round(expected_fee, 2),
                        "contracted_tax": round(expected_tax, 2),
                        "overcharge_amount": round(overcharge, 2)
                    })

        return {
            "contracted_sla_terms": GatewayConfig.get_sla_text(),
            "total_overcharged_orders": len(overcharged_list),
            "total_claimable_overcharge_inr": round(total_overcharge, 2),
            "discrepancy_details": overcharged_list
        }

    ALLOWED_TABLES = {"payments"}
    ALLOWED_COLUMNS = {"payment_id", "order_id", "status", "settlement_utr", "created_at"}

    @staticmethod
    def query_gateway_payments_db(filter_key=None, filter_value=None):
        """
        Read-only, strictly parameterized inspection of Razorpay Gateway 'payments' table.
        Client-side store tables ('orders', 'cart', 'products') are merchant private ledgers.
        Enforces read-only SQLite access mode for internal DB protection.
        """
        if not os.path.exists(STORE_DB_PATH):
            return {"status": "DB_NOT_FOUND", "message": "store.db does not exist yet."}

        try:
            db_uri = f"file:{os.path.abspath(STORE_DB_PATH)}?mode=ro"
            conn = sqlite3.connect(db_uri, uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Execute SELECT COUNT(*) to get true total transaction count in database
            cursor.execute("SELECT COUNT(*) FROM payments;")
            total_count = cursor.fetchone()[0]

            if filter_key and filter_value:
                clean_col = re.sub(r'[^a-zA-Z0-9_]', '', str(filter_key).lower())
                if clean_col not in ReconToolbox.ALLOWED_COLUMNS:
                    clean_col = "order_id"
                cursor.execute(f"SELECT * FROM payments WHERE {clean_col} LIKE ? LIMIT 100;", (f"%{str(filter_value).strip()}%",))
            else:
                cursor.execute("SELECT * FROM payments LIMIT 100;")

            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return {
                "gateway_table": "payments",
                "authority": "Razorpay Gateway Core Database (Read-Only Defense Active)",
                "total_records_in_db": total_count,
                "returned_records_count": len(rows),
                "records": rows,
                "note": "Client-side merchant store tables (orders/cart/products) are private client data and cannot be queried directly from gateway DB."
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    @staticmethod
    def calculate_tax_breakdown(base_amount: float, tax_rate_pct: float = 18.0) -> dict:
        """
        Calculates pure GST tax amount and total deduction on a base MDR processing fee or transaction amount.
        """
        try:
            base = float(base_amount)
            rate = float(tax_rate_pct)
            calculated_gst = round((base * rate) / 100.0, 2)
            total_deduction = round(base + calculated_gst, 2)
            return {
                "base_amount_inr": base,
                "tax_rate_percent": f"{rate:.2f}%",
                "calculated_gst_tax_inr": calculated_gst,
                "total_amount_including_tax_inr": total_deduction,
                "statutory_note": f"Standard Indian GST ({rate:.0f}%) applied under Section 9 of CGST Act."
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    @staticmethod
    def generate_dispute_ticket(session_data, order_ids=None, reason="Gateway MDR SLA Overcharge"):
        fee_audit = ReconToolbox.calculate_fee_discrepancies(session_data)
        discrepancies = fee_audit.get("discrepancy_details", [])

        if order_ids and isinstance(order_ids, list) and len(order_ids) > 0:
            target_discrepancies = [d for d in discrepancies if d["order_id"] in order_ids]
            if not target_discrepancies:
                target_discrepancies = discrepancies
        else:
            target_discrepancies = discrepancies

        orders_summary = []
        total_claim = 0.0

        for d in target_discrepancies:
            claim_val = float(d.get("overcharge_amount", 0.0))
            total_claim += claim_val
            orders_summary.append({
                "order_id": d["order_id"],
                "payment_id": d["payment_id"],
                "settlement_utr": d["settlement_utr"],
                "billed_amount": f"INR {float(d['billed_amount']):,.2f}",
                "charged_mdr": f"INR {float(d['charged_fee']):,.2f} + GST INR {float(d['charged_tax']):,.2f}",
                "contracted_mdr": f"INR {float(d['contracted_fee']):,.2f} + GST INR {float(d['contracted_tax']):,.2f}",
                "claim_amount": f"INR {claim_val:,.2f}"
            })

        return {
            "ticket_type": "OFFICIAL_MERCHANT_DISPUTE_CLAIM",
            "from_email": "merchant-disputes@freshmart-store.com",
            "to_email": "merchant-support@razorpay.com",
            "subject": f"URGENT: MDR Fee Overcharge Dispute Claim - Batch Ref #{len(target_discrepancies)} Orders",
            "total_claim_amount_inr": round(total_claim, 2),
            "contracted_sla_terms": GatewayConfig.get_sla_text(),
            "disputed_orders": orders_summary,
            "dispute_reason": reason
        }
