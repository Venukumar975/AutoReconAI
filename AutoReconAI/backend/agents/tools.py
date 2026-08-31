import os
import re
import sqlite3
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from config_loader import GatewayConfig

POSSIBLE_DB_PATHS = [
    os.path.join(BACKEND_DIR, "..", "store.db"),
    os.path.join(BACKEND_DIR, "..", "..", "store.db"),
    os.path.join(CURRENT_DIR, "store.db"),
    os.path.abspath("store.db")
]
STORE_DB_PATH = next((p for p in POSSIBLE_DB_PATHS if os.path.exists(os.path.abspath(p))), os.path.abspath(os.path.join(BACKEND_DIR, "..", "store.db")))


class ReconToolbox:

    @staticmethod
    def get_reconciliation_overview(session_data):
        orders = session_data.get("orders", [])
        settlements = session_data.get("settlements", [])
        bank_txns = session_data.get("bank_txns", [])

        if not orders or not settlements or not bank_txns:
            return {
                "status": "NO_SESSION_DATA",
                "message": "No active reconciliation data loaded. Please ensure Store Orders CSV, Bank Statement (PDF/Excel) and Settlement CSV are uploaded."
            }

        orders_by_id = {o["order_id"]: o for o in orders}

        total_settlement_txns = len(settlements)
        total_store_orders = len(orders)
        
        # Calculate gross metrics from settlements
        positive_settlements = [s for s in settlements if float(s.get("net_credit", 0.0)) > 0]
        total_gmv = sum(float(s.get("amount", 0.0)) for s in positive_settlements) or sum(float(o.get("gross_amount", 0.0)) for o in orders)
        total_fees = sum(float(s.get("fee", 0.0)) for s in positive_settlements)
        total_gst = sum(float(s.get("tax", 0.0)) for s in positive_settlements)
        total_tds = sum(float(s.get("tds", 0.0)) for s in positive_settlements)
        total_bank_deposited = sum(float(b.get("credit", 0.0)) for b in bank_txns if b.get("is_gateway_credit"))

        contracted_mdr = GatewayConfig.get_mdr_rate()
        gst_rate = GatewayConfig.get_gst_rate()
        mdr_threshold = contracted_mdr + 0.0005 # To remove rounding errors and improve precision 

        dropped_webhooks = []
        fee_overcharges = []
        orphan_refunds = []
        chargeback_holds = []
        tds_orders = []

        total_overcharge_cash = 0.0
        total_chargeback_debit = 0.0

        for s in settlements:
            oid = s["order_id"]
            amount = float(s.get("amount", 0.0))
            fee = float(s.get("fee", 0.0))
            tax = float(s.get("tax", 0.0))
            tds_val = float(s.get("tds", 0.0))
            net_credit = float(s.get("net_credit", 0.0))
            status_val = str(s.get("status", "")).lower()
            txn_type = str(s.get("type", "")).lower()
            pid = str(s.get("payment_id", ""))

            order_info = orders_by_id.get(oid)
            order_status = order_info.get("order_status") if order_info else "UNKNOWN"

            # 1. Dropped webhook
            if order_info and order_status == "PENDING" and status_val == "captured":
                dropped_webhooks.append(oid)

            # 2. MDR fee overcharge against dynamic config
            fee_rate = (fee / amount) if amount > 0 else 0.0
            if fee_rate > mdr_threshold and status_val == "captured":
                fee_overcharges.append(oid)
                expected_fee = amount * contracted_mdr
                expected_tax = expected_fee * gst_rate
                overcharge_delta = (fee + tax) - (expected_fee + expected_tax)
                if overcharge_delta > 0:
                    total_overcharge_cash += overcharge_delta

            # 3. Bank Chargeback Dispute Holds
            if status_val == "dispute_hold" or txn_type == "dispute_hold" or pid.startswith("disp_"):
                chargeback_holds.append(oid)
                total_chargeback_debit += abs(net_credit)

            # 4. Orphan customer refunds (Prior-period return deductions or negative refunds)
            elif status_val == "refunded" or txn_type == "refund" or pid.startswith("rfnd_") or (oid not in orders_by_id and net_credit < 0):
                orphan_refunds.append(oid)

            # 5. Section 194-O TDS deductions
            if tds_val > 0:
                tds_orders.append(oid)

        unique_mismatched = sorted(list(set(dropped_webhooks + fee_overcharges + orphan_refunds + chargeback_holds)))
        mismatched_count = len(unique_mismatched)
        matched_count = max(0, total_settlement_txns - mismatched_count)
        match_rate = round((matched_count / max(total_settlement_txns, 1)) * 100, 1)

        # Calculate refund fee leakage for orphan customer refunds
        total_orphan_refund_fee_loss = 0.0
        for s in settlements:
            oid = s["order_id"]
            pid = str(s.get("payment_id", ""))
            if oid in orphan_refunds and not pid.startswith("disp_"):
                fee = float(s.get("fee", 0.0))
                tax = float(s.get("tax", 0.0))
                total_orphan_refund_fee_loss += (fee + tax)

        # Pre-format Master 5-Way Mismatch Summary Table (Template 5)
        summary_table_lines = [
            "| # | Mismatch Category | Affected Count | Sample Order IDs | Money Lost? (Yes/No) | Lost Amount (INR) | Recoverable / Held / Frozen Amount (INR) | AI Controller Action |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            f"| 1 | Fee Overcharges | {len(set(fee_overcharges))} | {', '.join(sorted(list(set(fee_overcharges)))[:4]) or '-'} | Yes | ₹{total_overcharge_cash:,.2f} | ₹{total_overcharge_cash:,.2f} (Recoverable) | Auto-draft Razorpay SLA dispute ticket |",
            f"| 2 | Dropped Webhooks | {len(set(dropped_webhooks))} | {', '.join(sorted(list(set(dropped_webhooks)))[:4]) or '-'} | No | - | ₹0.00 (Safe) | Manually fulfill pending order in store dashboard |",
            f"| 3 | Orphan Customer Refunds | {len(set(orphan_refunds))} | {', '.join(sorted(list(set(orphan_refunds)))[:4]) or '-'} | Yes (Fee Leakage) | ₹{total_orphan_refund_fee_loss:,.2f} | ₹0.00 (Unrecoverable) | Post internal journal to Returns & Allowances ledger |",
            f"| 4 | Bank Chargeback Holds | {len(set(chargeback_holds))} | {', '.join(sorted(list(set(chargeback_holds)))[:4]) or '-'} | Pending | - | ₹{total_chargeback_debit:,.2f} (Held in Escrow) | Submit Proof of Delivery (PoD) within 7 days |",
            f"| 5 | Section 194-O TDS | {len(set(tds_orders))} | {('All Captured Orders' if len(tds_orders) > 0 else 'None (Disabled)')} | No | - | ₹{total_tds:,.2f} (Tax Asset Credit) | Reconcile in Form 26AS / Annual ITR filing |"
        ]

        return {
            "total_settlement_transactions": total_settlement_txns,
            "total_store_orders": total_store_orders,
            "total_gmv_inr": round(total_gmv, 2),
            "total_gateway_fees_inr": round(total_fees, 2),
            "total_gst_inr": round(total_gst, 2),
            "total_tds_inr": round(total_tds, 2),
            "total_bank_deposited_inr": round(total_bank_deposited, 2),
            "match_rate": f"{match_rate}%",
            "matched_transactions_count": matched_count,
            "mismatched_transactions_count": mismatched_count,
            "contracted_sla_terms": GatewayConfig.get_sla_text(),
            "default_table_md": "\n".join(summary_table_lines),
            "mismatch_categories": {
                "dropped_webhooks": {
                    "count": len(set(dropped_webhooks)),
                    "order_ids": sorted(list(set(dropped_webhooks)))
                },
                "fee_overcharges": {
                    "count": len(set(fee_overcharges)),
                    "order_ids": sorted(list(set(fee_overcharges))),
                    "recoverable_cash_inr": round(total_overcharge_cash, 2)
                },
                "orphan_refunds": {
                    "count": len(set(orphan_refunds)),
                    "order_ids": sorted(list(set(orphan_refunds)))
                },
                "chargeback_holds": {
                    "count": len(set(chargeback_holds)),
                    "order_ids": sorted(list(set(chargeback_holds))),
                    "held_amount_inr": round(total_chargeback_debit, 2)
                },
                "section_194o_tds": {
                    "count": len(set(tds_orders)),
                    "total_tds_inr": round(total_tds, 2),
                    "is_tds_applicable": GatewayConfig.is_tds_applicable()
                }
            }
        }

    @staticmethod
    def calculate_refund_fee_leakage(session_data):
        """
        Audits voluntary customer refunds ONLY (Edge Case 3).
        Strictly excludes bank chargeback dispute holds (disp_xxxx).
        Distinguishes between Orphan Refunds (ORD_PRIOR_) and Same-Month Customer Refunds (ORD_xxxx).
        """
        settlements = session_data.get("settlements", [])
        orders = session_data.get("orders", [])
        orders_by_id = {o["order_id"]: o for o in orders}

        refund_entries = []
        for s in settlements:
            status_val = str(s.get("status", "")).lower()
            txn_type = str(s.get("type", "")).lower()
            pid = str(s.get("payment_id", ""))
            oid = str(s.get("order_id", ""))

            # Strictly EXCLUDE bank chargeback dispute holds
            if status_val == "dispute_hold" or txn_type == "dispute_hold" or pid.startswith("disp_"):
                continue

            # Voluntary customer refund criteria
            if (
                txn_type == "refund" or 
                status_val == "refunded" or 
                pid.startswith("rfnd_") or 
                oid.startswith("ORD_PRIOR_") or 
                (oid not in orders_by_id and float(s.get("net_credit", 0.0)) < 0)
            ):
                refund_entries.append(s)

        refund_details = []
        orphan_count = 0
        intra_period_count = 0
        total_refund_gmv = 0.0
        total_fee_leakage = 0.0

        for r in refund_entries:
            oid = r.get("order_id", "-")
            amt = float(r.get("amount", 0.0))
            if amt == 0.0 and float(r.get("net_credit", 0.0)) < 0:
                amt = abs(float(r.get("net_credit", 0.0)))
            fee = float(r.get("fee", 0.0))
            tax = float(r.get("tax", 0.0))
            unreversed_loss = round(fee + tax, 2)
            total_refund_gmv += amt
            total_fee_leakage += unreversed_loss

            is_orphan = oid.startswith("ORD_PRIOR_") or (oid not in orders_by_id)
            if is_orphan:
                orphan_count += 1
                classification = "Orphan Refund (Prior Period)"
            else:
                intra_period_count += 1
                classification = "Same-Month Customer Refund"

            order_info = orders_by_id.get(oid)
            raw_dt = r.get("created_at") or (order_info.get("created_at") if order_info else "") or ""
            date_str = str(raw_dt)[:10] if raw_dt else "-"

            refund_details.append({
                "date": date_str,
                "order_id": oid,
                "payment_id": r.get("payment_id", "-"),
                "refund_amount": round(amt, 2),
                "retained_mdr_fee": round(fee, 2),
                "retained_gst_tax": round(tax, 2),
                "unreversed_fee_loss": unreversed_loss,
                "settlement_utr": r.get("settlement_utr", "-"),
                "classification": classification
            })

        # Pre-format default_table_md for Refund Fee Loss
        refund_table_lines = [
            "| Date | Order ID | Payment ID | Settlement UTR | Refund Amount (INR) | Retained MDR (INR) | Retained GST (18%) (INR) | Un-Reversed Cash Loss (INR) | Classification |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]
        for rd in refund_details:
            refund_table_lines.append(
                f"| {rd.get('date', '-')} | {rd['order_id']} | {rd['payment_id']} | {rd['settlement_utr']} | ₹{rd['refund_amount']:,.2f} | ₹{rd['retained_mdr_fee']:,.2f} | ₹{rd['retained_gst_tax']:,.2f} | ₹{rd['unreversed_fee_loss']:,.2f} | {rd['classification']} |"
            )
        refund_table_lines.append(
            f"| **TOTALS** | **{len(refund_entries)} Refunds** | - | - | **₹{total_refund_gmv:,.2f}** | - | - | **₹{total_fee_leakage:,.2f}** | **{orphan_count} Orphan / {intra_period_count} Intra-Period** |"
        )

        return {
            "total_refund_entries": len(refund_entries),
            "orphan_refund_count": orphan_count,
            "intra_period_refund_count": intra_period_count,
            "total_refund_gmv_inr": round(total_refund_gmv, 2),
            "total_fee_leakage_inr": round(total_fee_leakage, 2),
            "claimable_from_gateway_inr": 0.00,
            "refund_policy_note": "Razorpay transaction fees and GST are permanently non-refundable on customer-initiated refunds.",
            "default_table_md": "\n".join(refund_table_lines),
            "refund_details": refund_details
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

        # Pre-format default_table_md for Mismatches List
        mismatch_table_lines = [
            "| Order ID | Payment ID | Settlement UTR | Billed Amount (INR) | Store Status | Detected Anomalies | Required Action |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]
        for res in results:
            issues = "; ".join(a["issue"] for a in res["anomalies"])
            actions = "; ".join(a["action_required"] for a in res["anomalies"])
            mismatch_table_lines.append(
                f"| {res['order_id']} | {res['payment_id']} | {res['settlement_utr']} | ₹{res['billed_amount']:,.2f} | {res['store_status']} | {issues} | {actions} |"
            )

        return {
            "total_mismatched_orders": len(results),
            "filter_applied": category,
            "default_table_md": "\n".join(mismatch_table_lines),
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
        matching_settlements = [s for s in settlements if s.get("order_id") == clean_oid]

        # Separate captured payment vs dispute hold vs refund entries
        payment_record = next((s for s in matching_settlements if str(s.get("type", "")).lower() != "dispute_hold" and not str(s.get("payment_id", "")).startswith("disp_") and str(s.get("status", "")).lower() != "dispute_hold"), None)
        dispute_record = next((s for s in matching_settlements if str(s.get("type", "")).lower() == "dispute_hold" or str(s.get("payment_id", "")).startswith("disp_") or str(s.get("status", "")).lower() == "dispute_hold"), None)
        refund_record = next((s for s in matching_settlements if str(s.get("status", "")).lower() == "refunded" or str(s.get("type", "")).lower() == "refund" or str(s.get("payment_id", "")).startswith("rfnd_")), None)

        # Primary settlement record for bank matching
        primary_settlement = payment_record or dispute_record or (matching_settlements[0] if matching_settlements else None)
        matched_utr = primary_settlement.get("settlement_utr") if primary_settlement else None
        bank_record = next((b for b in bank_txns if b.get("extracted_utr") == matched_utr and matched_utr != "-"), None) if matched_utr else None

        actual_fee_rate = 0.0
        overcharge_amount = 0.0
        contracted_mdr = GatewayConfig.get_mdr_rate()
        gst_rate = GatewayConfig.get_gst_rate()
        mdr_threshold = contracted_mdr + 0.0005

        if payment_record:
            amt = float(payment_record.get("amount", 0.0))
            fee = float(payment_record.get("fee", 0.0))
            tax = float(payment_record.get("tax", 0.0))
            if amt > 0:
                actual_fee_rate = (fee / amt) * 100.0
                if actual_fee_rate > (mdr_threshold * 100.0):
                    expected_fee = amt * contracted_mdr
                    expected_tax = expected_fee * gst_rate
                    overcharge_amount = (fee + tax) - (expected_fee + expected_tax)

        is_chargeback = dispute_record is not None
        dispute_gmv = float(dispute_record.get("amount", 0.0)) if dispute_record else 0.0
        dispute_fee = float(dispute_record.get("fee", 0.0)) if dispute_record else 0.0
        dispute_tax = float(dispute_record.get("tax", 0.0)) if dispute_record else 0.0
        dispute_escrow_debit = float(dispute_record.get("net_credit", 0.0)) if dispute_record else 0.0

        is_refund = refund_record is not None
        refund_amt = float(refund_record.get("amount", 0.0)) if refund_record else 0.0

        is_dropped_webhook = bool(order_record and order_record.get("order_status") == "PENDING" and payment_record)
        is_fee_overcharge = actual_fee_rate > (mdr_threshold * 100.0)

        diagnosis_parts = []
        if is_chargeback:
            diagnosis_parts.append(f"Bank Chargeback Dispute Hold: INR {abs(dispute_escrow_debit):,.2f} debited to escrow (GMV INR {dispute_gmv:,.2f} + INR {dispute_fee+dispute_tax:,.2f} penalty fee). Submit Proof of Delivery within 7 days.")
        if is_fee_overcharge:
            diagnosis_parts.append(f"MDR SLA Overcharge: Billed at {actual_fee_rate:.2f}% vs contracted {contracted_mdr*100:.2f}% SLA. Recoverable: INR {overcharge_amount:,.2f}.")
        if is_dropped_webhook:
            diagnosis_parts.append("Dropped Webhook: Store order is PENDING while payment was captured. Fulfill order manually.")
        if is_refund:
            diagnosis_parts.append(f"Customer Refund: Processed refund of INR {refund_amt:,.2f}.")
        if not diagnosis_parts:
            diagnosis_parts.append("Transaction reconciled 100% cleanly across all 3 ledgers with zero discrepancies.")

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
                "present": bool(payment_record or dispute_record),
                "payment_id": payment_record.get("payment_id") if payment_record else (dispute_record.get("payment_id") if dispute_record else "N/A"),
                "billed_amount": payment_record.get("amount", 0.0) if payment_record else (dispute_record.get("amount", 0.0) if dispute_record else 0.0),
                "fee_charged": payment_record.get("fee", 0.0) if payment_record else 0.0,
                "tax_charged": payment_record.get("tax", 0.0) if payment_record else 0.0,
                "effective_fee_rate": f"{actual_fee_rate:.2f}%",
                "net_credit": payment_record.get("net_credit", 0.0) if payment_record else 0.0,
                "settlement_utr": matched_utr if matched_utr else "N/A"
            },
            "bank_statement_ledger": {
                "present": bool(bank_record),
                "deposit_amount": bank_record.get("credit", 0.0) if bank_record else 0.0,
                "deposit_date": bank_record.get("txn_date") if bank_record else "N/A",
                "narration": bank_record.get("primary_narration") if bank_record else "N/A",
                "matched_utr": bank_record.get("extracted_utr") if bank_record else "N/A"
            },
            "chargeback_dispute_details": {
                "is_chargeback_hold": is_chargeback,
                "dispute_payment_id": dispute_record.get("payment_id") if dispute_record else None,
                "disputed_order_amount": dispute_gmv,
                "dispute_handling_fee": dispute_fee,
                "dispute_gst": dispute_tax,
                "total_penalty_fee": dispute_fee + dispute_tax,
                "total_escrow_debit_inr": abs(dispute_escrow_debit),
                "action_required": "Submit Proof of Delivery (AWB tracking + Invoice) within 7-day SLA window to recover held funds." if is_chargeback else "None"
            },
            "financial_audit_diagnosis": {
                "is_chargeback_hold": is_chargeback,
                "is_dropped_webhook": is_dropped_webhook,
                "is_fee_overcharge": is_fee_overcharge,
                "is_orphan_refund": is_refund,
                "contracted_sla_rate": GatewayConfig.get_sla_text(),
                "overcharge_amount_inr": round(overcharge_amount, 2),
                "escrow_held_amount_inr": round(abs(dispute_escrow_debit), 2) if is_chargeback else 0.0,
                "diagnosis_summary": " | ".join(diagnosis_parts),
                "recommended_action": diagnosis_parts[0]
            }
        }

    @staticmethod
    def calculate_fee_discrepancies(session_data):
        settlements = session_data.get("settlements", [])
        orders = session_data.get("orders", [])
        orders_by_id = {o["order_id"]: o for o in orders}

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
            status_val = str(s.get("status", "")).lower()
            txn_type = str(s.get("type", "")).lower()
            pid = str(s.get("payment_id", ""))

            # Exclude customer bank chargeback dispute holds and refunds from MDR fee overcharge calculations
            if status_val == "dispute_hold" or txn_type == "dispute_hold" or pid.startswith("disp_") or status_val == "refunded" or txn_type == "refund" or pid.startswith("rfnd_"):
                continue

            rate = (fee / amount) if amount > 0 else 0.0

            order_info = orders_by_id.get(oid)
            raw_dt = s.get("created_at") or (order_info.get("created_at") if order_info else "") or ""
            date_str = str(raw_dt)[:10] if raw_dt else "-"

            if rate > mdr_threshold:
                expected_fee = amount * contracted_mdr
                expected_tax = expected_fee * gst_rate
                overcharge = (fee + tax) - (expected_fee + expected_tax)
                if overcharge > 0:
                    total_overcharge += overcharge
                    overcharged_list.append({
                        "date": date_str,
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

        # Dynamically impute SLA header parameters from GatewayConfig!
        contracted_mdr_pct = contracted_mdr * 100.0
        gst_rate_pct = gst_rate * 100.0
        sla_effective_pct = contracted_mdr_pct * (1.0 + gst_rate)
        sla_header = f"Contracted Fee + Tax ({contracted_mdr_pct:.2f}% MDR + {gst_rate_pct:.2f}% GST = {sla_effective_pct:.2f}% SLA)"

        table_lines = [
            f"| Date | Order ID | Payment ID | Settlement UTR | Billed Amount (INR) | Charged Fee + Tax (INR) | Effective Rate | {sla_header} | Overcharge Amount (INR) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]

        total_billed = 0.0
        total_charged = 0.0
        total_contracted = 0.0

        for item in overcharged_list:
            t_date = item.get("date", "-")
            t_oid = item["order_id"]
            t_pid = item["payment_id"]
            t_utr = item["settlement_utr"]
            t_billed = item["billed_amount"]
            t_charged = item["charged_fee"] + item["charged_tax"]
            t_eff_rate = item["effective_charged_rate"]
            t_contracted = item["contracted_fee"] + item["contracted_tax"]
            t_overcharge = item["overcharge_amount"]

            total_billed += t_billed
            total_charged += t_charged
            total_contracted += t_contracted

            table_lines.append(
                f"| {t_date} | {t_oid} | {t_pid} | {t_utr} | ₹{t_billed:,.2f} | ₹{t_charged:,.2f} | {t_eff_rate} | ₹{t_contracted:,.2f} | ₹{t_overcharge:,.2f} |"
            )

        table_lines.append(
            f"| **TOTALS** | **{len(overcharged_list)} Orders** | - | - | **₹{total_billed:,.2f}** | **₹{total_charged:,.2f}** | - | **₹{total_contracted:,.2f}** | **₹{total_overcharge:,.2f}** |"
        )

        default_table_md = "\n".join(table_lines)

        return {
            "contracted_sla_terms": GatewayConfig.get_sla_text(),
            "total_overcharged_orders": len(overcharged_list),
            "total_claimable_overcharge_inr": round(total_overcharge, 2),
            "default_table_md": default_table_md,
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

    @staticmethod
    def audit_chargeback_holds(session_data):
        """
        Audits all customer bank chargebacks & dispute holds (Edge Case 4).
        Pre-formats Template 3 table with dispute IDs, fees, GST, and escrow debits.
        """
        settlements = session_data.get("settlements", [])
        orders = session_data.get("orders", [])
        orders_by_id = {o["order_id"]: o for o in orders}

        if not settlements:
            return {"status": "NO_DATA", "message": "No settlement data available."}

        chargebacks_list = []
        total_disputed_gmv = 0.0
        total_dispute_fees = 0.0
        total_dispute_tax = 0.0
        total_escrow_held = 0.0

        for s in settlements:
            status_val = str(s.get("status", "")).lower()
            txn_type = str(s.get("type", "")).lower()
            pid = str(s.get("payment_id", ""))

            if status_val == "dispute_hold" or txn_type == "dispute_hold" or pid.startswith("disp_"):
                oid = s.get("order_id", "-")
                amt = float(s.get("amount", 0.0))
                fee = float(s.get("fee", 0.0))
                tax = float(s.get("tax", 0.0))
                net_credit = float(s.get("net_credit", 0.0))
                utr = s.get("settlement_utr", "-")

                order_info = orders_by_id.get(oid)
                raw_dt = s.get("created_at") or (order_info.get("created_at") if order_info else "") or ""
                date_str = str(raw_dt)[:10] if raw_dt else "-"

                total_disputed_gmv += amt
                total_dispute_fees += fee
                total_dispute_tax += tax
                total_escrow_held += abs(net_credit)

                chargebacks_list.append({
                    "date": date_str,
                    "order_id": oid,
                    "customer_name": order_info.get("customer_name") if order_info else "N/A",
                    "payment_id": pid,
                    "settlement_utr": utr,
                    "disputed_order_amount": round(amt, 2),
                    "dispute_fee": round(fee, 2),
                    "dispute_tax": round(tax, 2),
                    "total_penalty_fee": round(fee + tax, 2),
                    "total_escrow_debit": round(net_credit, 2),
                    "order_status_in_store": order_info.get("order_status") if order_info else "UNKNOWN",
                    "payment_timestamp": raw_dt
                })

        table_lines = [
            "| Date | Order ID | Dispute Payment ID | Settlement UTR | Disputed Order GMV (INR) | Dispute Handling Fee (INR) | GST on Fee (18%) (INR) | Total Escrow Debit (INR) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]

        for item in chargebacks_list:
            table_lines.append(
                f"| {item['date']} | {item['order_id']} | {item['payment_id']} | {item['settlement_utr']} | ₹{item['disputed_order_amount']:,.2f} | ₹{item['dispute_fee']:,.2f} | ₹{item['dispute_tax']:,.2f} | ₹{item['total_escrow_debit']:,.2f} |"
            )

        if chargebacks_list:
            table_lines.append(
                f"| **TOTALS** | **{len(chargebacks_list)} Disputed Orders** | - | - | **₹{total_disputed_gmv:,.2f}** | **₹{total_dispute_fees:,.2f}** | **₹{total_dispute_tax:,.2f}** | **-₹{total_escrow_held:,.2f}** |"
            )
        else:
            table_lines.append("| - | No Active Chargeback Holds | - | - | ₹0.00 | ₹0.00 | ₹0.00 | ₹0.00 |")

        default_table_md = "\n".join(table_lines)

        defense_guidance = (
            "Under Visa/Mastercard and RBI regulations, this amount has been placed on temporary hold following a customer-initiated bank chargeback. "
            "If these orders were legitimately fulfilled and delivered, submit your Proof of Delivery (Courier AWB tracking & Tax Invoice) to Razorpay Merchant Support "
            "within the 7-day SLA window to contest and recover the funds."
        )

        return {
            "total_chargeback_orders": len(chargebacks_list),
            "total_disputed_gmv_inr": round(total_disputed_gmv, 2),
            "total_dispute_penalty_inr": round(total_dispute_fees + total_dispute_tax, 2),
            "total_escrow_debit_inr": round(total_escrow_held, 2),
            "default_table_md": default_table_md,
            "defense_guidance": defense_guidance,
            "chargeback_details": chargebacks_list
        }

    @staticmethod
    def audit_tax_and_tds_deductions(session_data):
        """
        Audits Section 194-O TDS and GST Input Tax Credit on Gateway MDR (Template 4).
        Dual-mode: adapts dynamically based on whether IS_TDS_APPLICABLE is enabled or disabled.
        """
        settlements = session_data.get("settlements", [])
        orders = session_data.get("orders", [])
        orders_by_id = {o["order_id"]: o for o in orders}

        if not settlements:
            return {"status": "NO_DATA", "message": "No settlement data available."}

        is_tds_active = GatewayConfig.is_tds_applicable()
        contracted_mdr = GatewayConfig.get_mdr_rate()
        gst_rate = GatewayConfig.get_gst_rate()
        tax_profile = GatewayConfig.get_merchant_tax_profile()

        captured_settlements = [s for s in settlements if s.get("status") == "captured" and float(s.get("net_credit", 0.0)) > 0]

        total_gmv = sum(float(s.get("amount", 0.0)) for s in captured_settlements)
        total_mdr = sum(float(s.get("fee", 0.0)) for s in captured_settlements)
        total_gst = sum(float(s.get("tax", 0.0)) for s in captured_settlements)
        total_tds = sum(float(s.get("tds", 0.0)) for s in captured_settlements)

        # Table 1: Section 194-O TDS Breakdown
        tds_table_lines = [
            "### 1. Section 194-O Statutory TDS Audit (Direct Income Tax)",
            "| Metric / Parameter | Value | Statutory Regulatory Reference | Accounting Ledger Routing |",
            "| :--- | :--- | :--- | :--- |",
            f"| TDS Applicability Status | **{'ACTIVE (1.00% Withholding)' if is_tds_active else 'NOT APPLICABLE (0.00%)'}** | Section 194-O of Income Tax Act, 1961 | Form 26AS Tax Credit |",
            f"| Merchant PAN Card | `{tax_profile['pan']}` | Section 206AA Verification | PAN Ledger Asset |",
            f"| Merchant GSTIN | `{tax_profile['gstin']}` | E-Commerce Operator Mandate | Statutory Tax Profile |",
            f"| Total Gross Sales Audited | ₹{total_gmv:,.2f} | 100% Captured Order GMV | Sales Revenue Account |",
            f"| **Total Section 194-O TDS Withheld** | **₹{total_tds:,.2f}** | **1.00% Withheld by Gateway** | **TDS Receivable (Form 26AS Asset)** |"
        ]

        # Table 2: GST Input Tax Credit (ITC) on Payment Gateway Processing Fees
        itc_table_lines = [
            "### 2. GST Input Tax Credit (ITC) Statement (Indirect Tax on Gateway MDR)",
            "| Parameter | Total Amount (INR) | GST Return Form | Claimable Input Tax Credit (ITC) |",
            "| :--- | :--- | :--- | :--- |",
            f"| Total Payment Gateway MDR Fees | ₹{total_mdr:,.2f} | Monthly Gateway Tax Invoice | Commercial Operating Expense |",
            f"| **18% Input GST Paid on MDR** | **₹{total_gst:,.2f}** | **GSTR-2B Auto-Drafted / Table 4(A)(5) GSTR-3B** | **100% Eligible Input Tax Credit (₹{total_gst:,.2f})** |"
        ]

        combined_tables_md = "\n".join(tds_table_lines) + "\n\n" + "\n".join(itc_table_lines)

        tds_statement = (
            f"INR {total_tds:,.2f} withheld by Razorpay is credited against your PAN in Form 26AS as Advance Income Tax."
            if is_tds_active and total_tds > 0
            else "Section 194-O TDS withholding was ₹0.00 for this settlement batch (no advance tax withheld by gateway)."
        )

        return {
            "is_tds_applicable": is_tds_active,
            "merchant_tax_profile": tax_profile,
            "total_gmv_inr": round(total_gmv, 2),
            "total_mdr_fees_inr": round(total_mdr, 2),
            "total_input_gst_itc_inr": round(total_gst, 2),
            "total_section_194o_tds_inr": round(total_tds, 2),
            "default_table_md": combined_tables_md,
            "accounting_guidance": (
                f"1. Section 194-O TDS: {tds_statement} "
                f"2. GST Input Tax Credit: INR {total_gst:,.2f} GST paid on Razorpay MDR is 100% claimable as Input Tax Credit (ITC) in Table 4(A)(5) of monthly GSTR-3B to offset grocery sales tax liability."
            )
        }
