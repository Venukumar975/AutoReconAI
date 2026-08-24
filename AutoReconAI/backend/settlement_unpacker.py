"""
AutoReconAI - Settlement Unpacker & Tax/Sales Executive Engine
=============================================================
Unpacks lumped payment gateway settlements into:
1. Net Gross Sales (GMV)
2. Gateway MDR Expense / Processing Fees
3. Claimable 18% GST Input Tax Credit (ITC) for GSTR-2B filing
4. Order-level Edge Case Categorization (Overcharges, Dropped Webhooks, Orphan Refunds)
5. AI Financial Controller FAQs & Key Takeaways
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)

from config_loader import GatewayConfig


class SettlementUnpackerEngine:

    @staticmethod
    def unpack_settlements(session_data: dict) -> dict:
        orders = session_data.get("orders", [])
        settlements = session_data.get("settlements", [])
        bank_txns = session_data.get("bank_txns", [])

        if not settlements:
            return {
                "success": False,
                "error": "No settlement data available. Please upload files in Data Ingestion Hub first."
            }

        orders_by_id = {o["order_id"]: o for o in orders}

        contracted_mdr = GatewayConfig.get_mdr_rate()
        gst_rate = GatewayConfig.get_gst_rate()
        mdr_threshold = contracted_mdr + 0.0005

        total_settlement_count = len(settlements)
        total_store_orders_count = len(orders)

        total_gmv = 0.0
        total_mdr_fee = 0.0
        total_gst_itc = 0.0
        total_net_payout = 0.0

        clean_orders = []
        overcharge_orders = []
        dropped_webhook_orders = []
        orphan_refund_orders = []

        total_overcharge_amount = 0.0
        total_orphan_refund_amount = 0.0

        for s in settlements:
            oid = s.get("order_id", "")
            amount = float(s.get("amount", 0.0))
            fee = float(s.get("fee", 0.0))
            tax = float(s.get("tax", 0.0))
            net_credit = float(s.get("net_credit", 0.0))
            utr = s.get("settlement_utr", "-")
            payment_id = s.get("payment_id", "-")

            order_info = orders_by_id.get(oid)
            order_status = order_info.get("order_status") if order_info else "UNKNOWN"

            if amount > 0:
                total_gmv += amount
            total_mdr_fee += fee
            total_gst_itc += tax
            total_net_payout += net_credit

            fee_rate = (fee / amount) if amount > 0 else 0.0
            is_overcharged = (fee_rate > mdr_threshold)
            is_dropped_webhook = (order_status == "PENDING")
            is_orphan_refund = (oid not in orders_by_id or net_credit < 0)

            if is_orphan_refund:
                orphan_amt = abs(net_credit)
                total_orphan_refund_amount += orphan_amt
                orphan_refund_orders.append({
                    "order_id": oid,
                    "payment_id": payment_id,
                    "settlement_utr": utr,
                    "deduction_amount": round(orphan_amt, 2),
                    "reason": "Prior-period customer return deducted from current settlement batch"
                })
            elif is_dropped_webhook:
                dropped_webhook_orders.append({
                    "order_id": oid,
                    "payment_id": payment_id,
                    "amount": round(amount, 2),
                    "settlement_utr": utr,
                    "store_status": "PENDING",
                    "gateway_status": "CAPTURED",
                    "action": "Payment confirmed in settlement. Mark order as FULFILLED in store."
                })
            elif is_overcharged:
                expected_fee = amount * contracted_mdr
                expected_tax = expected_fee * gst_rate
                overcharge_variance = (fee + tax) - (expected_fee + expected_tax)
                if overcharge_variance > 0:
                    total_overcharge_amount += overcharge_variance
                overcharge_orders.append({
                    "order_id": oid,
                    "payment_id": payment_id,
                    "billed_amount": round(amount, 2),
                    "billed_rate": f"{fee_rate * 100:.2f}%",
                    "contracted_rate": f"{contracted_mdr * 100:.2f}%",
                    "charged_fee": round(fee, 2),
                    "charged_tax": round(tax, 2),
                    "claimable_overcharge": round(max(0.0, overcharge_variance), 2)
                })
            else:
                clean_orders.append(oid)

        # Proportions of Gross GMV for visual diagram
        gmv_safe = max(total_gmv, 1.0)
        net_payout_pct = round((total_net_payout / gmv_safe) * 100, 2)
        mdr_fee_pct = round((total_mdr_fee / gmv_safe) * 100, 2)
        gst_itc_pct = round((total_gst_itc / gmv_safe) * 100, 2)
        effective_take_rate = round(((total_mdr_fee + total_gst_itc) / gmv_safe) * 100, 2)

        # Call Agent 5: TaxOptimizerAI for dynamic generative executive insights & FAQs
        from agents.tax_optimizer_agent import TaxOptimizerAI
        unpacked_facts = {
            "total_gmv": round(total_gmv, 2),
            "net_bank_payout": round(total_net_payout, 2),
            "total_mdr_expense": round(total_mdr_fee, 2),
            "total_gst_itc": round(total_gst_itc, 2),
            "net_payout_pct": net_payout_pct,
            "mdr_pct": mdr_fee_pct,
            "gst_pct": gst_itc_pct,
            "effective_take_rate": effective_take_rate,
            "overcharge_claim_inr": round(total_overcharge_amount, 2),
            "overcharge_orders_count": len(overcharge_orders),
            "dropped_webhooks_count": len(dropped_webhook_orders),
            "orphan_refunds_count": len(orphan_refund_orders),
            "orphan_refunds_amount": round(total_orphan_refund_amount, 2),
            "contracted_sla_text": GatewayConfig.get_sla_text()
        }
        ai_response = TaxOptimizerAI.generate_tax_and_executive_insights(unpacked_facts)

        refunds_pct = round((total_orphan_refund_amount / gmv_safe) * 100, 2)

        return {
            "success": True,
            "contracted_sla": {
                "mdr_percent": round(contracted_mdr * 100, 2),
                "gst_percent": round(gst_rate * 100, 2),
                "sla_text": GatewayConfig.get_sla_text()
            },
            "unpacked_pillars": {
                "total_gmv": round(total_gmv, 2),
                "total_mdr_expense": round(total_mdr_fee, 2),
                "total_gst_itc": round(total_gst_itc, 2),
                "net_bank_payout": round(total_net_payout, 2),
                "total_customer_refunds": round(total_orphan_refund_amount, 2),
                "proportions": {
                    "net_payout_percent": net_payout_pct,
                    "mdr_expense_percent": mdr_fee_pct,
                    "gst_itc_percent": gst_itc_pct,
                    "refunds_percent": refunds_pct
                }
            },
            "categorized_buckets": {
                "clean_reconciled": {
                    "count": len(clean_orders),
                    "label": "Cleanly Reconciled Orders"
                },
                "fee_overcharges": {
                    "count": len(overcharge_orders),
                    "total_claimable_inr": round(total_overcharge_amount, 2),
                    "orders": overcharge_orders
                },
                "dropped_webhooks": {
                    "count": len(dropped_webhook_orders),
                    "orders": dropped_webhook_orders
                },
                "orphan_refunds": {
                    "count": len(orphan_refund_orders),
                    "total_deduction_inr": round(total_orphan_refund_amount, 2),
                    "orders": orphan_refund_orders
                }
            },
            "executive_summary": ai_response.get("executive_summary", ""),
            "financial_faqs": ai_response.get("financial_faqs", []),
            "generated_by": ai_response.get("generated_by", "TaxOptimizerAI")
        }
