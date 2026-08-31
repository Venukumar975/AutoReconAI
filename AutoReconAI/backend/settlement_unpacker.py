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
        total_gmv = sum(float(o.get("gross_amount", 0.0)) for o in orders)
        if total_gmv == 0.0:
            total_gmv = sum(float(s.get("amount", 0.0)) for s in settlements if float(s.get("net_credit", 0.0)) > 0)

        positive_settlements = [s for s in settlements if float(s.get("net_credit", 0.0)) > 0]
        refund_settlements = [s for s in settlements if float(s.get("net_credit", 0.0)) < 0 or s.get("type") == "refund"]

        total_mdr_fee = sum(float(s.get("fee", 0.0)) for s in positive_settlements)
        total_gst_itc = sum(float(s.get("tax", 0.0)) for s in positive_settlements)
        pos_net_payout = sum(float(s.get("net_credit", 0.0)) for s in positive_settlements)

        total_bank_credits = sum(float(b.get("credit", 0.0)) for b in bank_txns if b.get("is_gateway_credit"))
        total_deductions = sum(abs(float(s.get("net_credit", 0.0))) for s in refund_settlements)
        total_orphan_refund_amount = sum(abs(float(s.get("amount", 0.0))) if float(s.get("amount", 0.0)) != 0 else abs(float(s.get("net_credit", 0.0))) for s in refund_settlements)
        total_non_recoverable_refund_loss = sum(float(s.get("fee", 0.0)) + float(s.get("tax", 0.0)) for s in refund_settlements)

        total_net_payout = total_bank_credits if total_bank_credits > 0 else round(pos_net_payout - total_deductions, 2)

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

            fee_rate = (fee / amount) if amount > 0 else 0.0
            is_overcharged = (fee_rate > mdr_threshold)
            is_dropped_webhook = (order_status == "PENDING")
            is_orphan_refund = (oid not in orders_by_id or net_credit < 0)

            if is_orphan_refund:
                orphan_amt = abs(net_credit)
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

        # Import contracted rates directly from master config.ini via GatewayConfig
        contracted_mdr_pct = round(GatewayConfig.get_mdr_rate() * 100.0, 2)      # e.g. 2.00%
        contracted_gst_pct = round(GatewayConfig.get_gst_rate() * 100.0, 2)      # e.g. 18.00%
        effective_take_rate = round(GatewayConfig.get_effective_sla_rate() * 100.0, 2) # e.g. 2.36%

        mdr_fee_pct = contracted_mdr_pct
        gst_itc_pct = round(contracted_mdr_pct * GatewayConfig.get_gst_rate(), 2)

        # Calculate remaining gross allocation proportions
        total_settlement_volume = max(1.0, total_net_payout + total_mdr_fee + total_gst_itc + total_orphan_refund_amount + total_non_recoverable_refund_loss)
        refunds_pct = round((total_orphan_refund_amount / total_settlement_volume) * 100, 2)
        non_recoverable_loss_pct = round((total_non_recoverable_refund_loss / total_settlement_volume) * 100, 2)
        net_payout_pct = round(100.0 - (mdr_fee_pct + gst_itc_pct + refunds_pct + non_recoverable_loss_pct), 2)

        # Call Agent 5: TaxOptimizerAI for dynamic generative executive insights & FAQs
        from agents.tax_optimizer_agent import TaxOptimizerAI
        unpacked_facts = {
            "total_gmv": round(total_gmv, 2),
            "net_bank_payout": round(total_net_payout, 2),
            "gross_bank_payout": round(pos_net_payout, 2),
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

        return {
            "success": True,
            "contracted_sla": {
                "mdr_percent": contracted_mdr_pct,
                "gst_percent": contracted_gst_pct,
                "sla_text": GatewayConfig.get_sla_text()
            },
            "unpacked_pillars": {
                "total_gmv": round(total_gmv, 2),
                "total_mdr_expense": round(total_mdr_fee, 2),
                "total_gst_itc": round(total_gst_itc, 2),
                "gross_bank_payout": round(pos_net_payout, 2),
                "net_bank_payout": round(total_net_payout, 2),
                "total_customer_refunds": round(total_orphan_refund_amount, 2),
                "total_non_recoverable_refund_loss": round(total_non_recoverable_refund_loss, 2),
                "proportions": {
                    "net_payout_percent": net_payout_pct,
                    "mdr_expense_percent": mdr_fee_pct,
                    "gst_itc_percent": gst_itc_pct,
                    "refunds_percent": refunds_pct,
                    "non_recoverable_loss_percent": non_recoverable_loss_pct
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
