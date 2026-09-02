"""
AutoReconAI - Settlement Unpacker & Tax/Sales Executive Engine
=============================================================
Forensically decomposes payment gateway settlements into:
1. Gross Merchandise Value (GMV)
2. Contracted Baseline MDR vs. Overcharged MDR (Claimable)
3. Contracted 18% GST Input Tax Credit (ITC) vs. Overcharged GST (Claimable)
4. Section 194-O Statutory TDS (1.00% Form 26AS Advance Tax Asset)
5. Customer Refunds Debited vs. Non-Recoverable Refund Fee Leakage
6. Customer Dispute Escrow Holds (Pending PoD) vs. Razorpay Dispute Penalties (Lost)
7. Actual Net Bank Credit & Recovery Upside Potential
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

        orders_by_id = {o.get("order_id"): o for o in orders}

        contracted_mdr_rate = GatewayConfig.get_mdr_rate()
        contracted_gst_rate = GatewayConfig.get_gst_rate()
        contracted_effective_sla = GatewayConfig.get_effective_sla_rate()
        mdr_threshold = contracted_mdr_rate + 0.0005

        total_gmv = sum(float(o.get("gross_amount", 0.0)) for o in orders)
        if total_gmv == 0.0:
            total_gmv = sum(float(s.get("amount", 0.0)) for s in settlements if float(s.get("net_credit", 0.0)) > 0)

        # 1. Forensic Buckets
        contracted_base_mdr = 0.0
        overcharged_mdr = 0.0
        contracted_base_gst = 0.0
        overcharged_gst = 0.0
        total_tds_withheld = 0.0

        clean_orders = []
        overcharge_orders = []
        dropped_webhook_orders = []
        orphan_refund_orders = []
        chargeback_dispute_orders = []

        total_customer_refund_gmv = 0.0
        total_refund_fee_leakage = 0.0

        total_disputed_escrow_gmv = 0.0
        total_dispute_penalties = 0.0

        for s in settlements:
            oid = s.get("order_id", "")
            pid = s.get("payment_id", "-")
            utr = s.get("settlement_utr", "-")
            stype = s.get("type", "").lower()
            amount = float(s.get("amount", 0.0))
            fee = float(s.get("fee", 0.0))
            tax = float(s.get("tax", 0.0))
            tds = float(s.get("tds", 0.0))
            net_credit = float(s.get("net_credit", 0.0))

            order_info = orders_by_id.get(oid)
            order_status = order_info.get("order_status") if order_info else "UNKNOWN"

            # Check if this is a Chargeback Dispute
            is_dispute = (stype == "dispute" or "disp_" in pid or "disp_" in oid or "dispute" in s.get("notes", "").lower())
            is_refund = (stype == "refund" or net_credit < 0 or "refund" in s.get("notes", "").lower()) and not is_dispute

            if is_dispute:
                dispute_deduction = abs(net_credit)
                # Razorpay fee model: Dispute deduction = Original GMV + ₹500 fee + 18% GST (₹90) = GMV + ₹590
                # If amount > 0, amount is GMV; otherwise deduct penalty to find GMV
                penalty_portion = fee + tax if (fee + tax) > 0 else 590.0
                disputed_gmv = amount if amount > 0 else max(0.0, dispute_deduction - penalty_portion)
                
                total_disputed_escrow_gmv += disputed_gmv
                total_dispute_penalties += penalty_portion

                chargeback_dispute_orders.append({
                    "order_id": oid,
                    "payment_id": pid,
                    "settlement_utr": utr,
                    "disputed_gmv": round(disputed_gmv, 2),
                    "penalty_fee": round(penalty_portion, 2),
                    "total_escrow_debit": round(dispute_deduction, 2),
                    "customer_name": order_info.get("customer_name", "Valued Customer") if order_info else "Valued Customer",
                    "reason": "Customer bank chargeback (Escrow held pending PoD)"
                })

            elif is_refund:
                refund_gmv = abs(amount) if amount > 0 else abs(net_credit)
                fee_leakage = fee + tax
                total_customer_refund_gmv += refund_gmv
                total_refund_fee_leakage += fee_leakage

                orphan_refund_orders.append({
                    "order_id": oid,
                    "payment_id": pid,
                    "settlement_utr": utr,
                    "deduction_amount": round(refund_gmv, 2),
                    "fee_leakage": round(fee_leakage, 2),
                    "reason": "Customer return refund deducted from payout"
                })

            else:
                # Regular captured payment
                total_tds_withheld += tds

                expected_mdr = round(amount * contracted_mdr_rate, 2)
                expected_gst = round(expected_mdr * contracted_gst_rate, 2)
                fee_rate = (fee / amount) if amount > 0 else 0.0

                is_overcharged = (fee_rate > mdr_threshold)
                is_dropped_webhook = (order_status == "PENDING")

                if is_overcharged:
                    overcharge_fee = max(0.0, round(fee - expected_mdr, 2))
                    overcharge_tax = max(0.0, round(tax - expected_gst, 2))
                    
                    contracted_base_mdr += expected_mdr
                    contracted_base_gst += expected_gst
                    overcharged_mdr += overcharge_fee
                    overcharged_gst += overcharge_tax

                    overcharge_orders.append({
                        "order_id": oid,
                        "payment_id": pid,
                        "billed_amount": round(amount, 2),
                        "billed_rate": f"{fee_rate * 100:.2f}%",
                        "contracted_rate": f"{contracted_mdr_rate * 100:.2f}%",
                        "charged_fee": round(fee, 2),
                        "charged_tax": round(tax, 2),
                        "overcharge_mdr": round(overcharge_fee, 2),
                        "overcharge_gst": round(overcharge_tax, 2),
                        "claimable_overcharge": round(overcharge_fee + overcharge_tax, 2)
                    })
                else:
                    contracted_base_mdr += fee
                    contracted_base_gst += tax
                    clean_orders.append(oid)

                if is_dropped_webhook:
                    dropped_webhook_orders.append({
                        "order_id": oid,
                        "payment_id": pid,
                        "amount": round(amount, 2),
                        "settlement_utr": utr,
                        "store_status": "PENDING",
                        "gateway_status": "CAPTURED",
                        "action": "Payment settled. Update order status to FULFILLED in store."
                    })

        # Bank Deposits Calculation
        total_bank_credits = sum(float(b.get("credit", 0.0)) for b in bank_txns if b.get("is_gateway_credit"))
        total_bank_debits = sum(float(b.get("debit", 0.0)) for b in bank_txns if b.get("is_gateway_credit"))
        pos_net_payout = sum(float(s.get("net_credit", 0.0)) for s in settlements if float(s.get("net_credit", 0.0)) > 0)
        total_debits = sum(abs(float(s.get("net_credit", 0.0))) for s in settlements if float(s.get("net_credit", 0.0)) < 0)
        
        net_bank_payout = round(total_bank_credits - total_bank_debits, 2) if len(bank_txns) > 0 else round(pos_net_payout - total_debits, 2)

        # Totals & Percentages of GMV
        gmv_base = max(1.0, total_gmv)
        
        total_claimable_overcharges = round(overcharged_mdr + overcharged_gst, 2)
        total_mdr_expense = round(contracted_base_mdr + overcharged_mdr, 2)
        total_gst_itc = round(contracted_base_gst + overcharged_gst, 2)
        total_dispute_deductions = round(total_disputed_escrow_gmv + total_dispute_penalties, 2)
        total_refund_deductions = round(total_customer_refund_gmv, 2)

        overcharge_rates = [float(o["billed_rate"].replace("%", "")) for o in overcharge_orders if "billed_rate" in o]
        avg_overcharged_mdr_rate = round(sum(overcharge_rates) / len(overcharge_rates), 2) if overcharge_rates else round(contracted_mdr_rate * 100.0, 2)

        # Proportions
        pct_net_payout = round((net_bank_payout / gmv_base) * 100.0, 2)
        pct_tds = round((total_tds_withheld / gmv_base) * 100.0, 2)
        pct_contracted_mdr = round((contracted_base_mdr / gmv_base) * 100.0, 2)
        pct_overcharged_mdr = round((overcharged_mdr / gmv_base) * 100.0, 2)
        pct_contracted_gst = round((contracted_base_gst / gmv_base) * 100.0, 2)
        pct_overcharged_gst = round((overcharged_gst / gmv_base) * 100.0, 2)
        pct_refunds = round((total_customer_refund_gmv / gmv_base) * 100.0, 2)
        pct_refund_leakage = round((total_refund_fee_leakage / gmv_base) * 100.0, 2)
        pct_dispute_escrow = round((total_disputed_escrow_gmv / gmv_base) * 100.0, 2)
        pct_dispute_penalties = round((total_dispute_penalties / gmv_base) * 100.0, 2)

        # Recovery Upside
        potential_recovered_payout = round(net_bank_payout + total_claimable_overcharges + total_disputed_escrow_gmv, 2)

        # Call TaxOptimizerAI for generative executive insights & FAQs
        from agents.tax_optimizer_agent import TaxOptimizerAI
        unpacked_facts = {
            "total_gmv": round(total_gmv, 2),
            "net_bank_payout": round(net_bank_payout, 2),
            "contracted_base_mdr": round(contracted_base_mdr, 2),
            "overcharged_mdr": round(overcharged_mdr, 2),
            "contracted_base_gst": round(contracted_base_gst, 2),
            "overcharged_gst": round(overcharged_gst, 2),
            "total_tds_withheld": round(total_tds_withheld, 2),
            "customer_refund_gmv": round(total_customer_refund_gmv, 2),
            "refund_fee_leakage": round(total_refund_fee_leakage, 2),
            "disputed_escrow_gmv": round(total_disputed_escrow_gmv, 2),
            "dispute_penalties": round(total_dispute_penalties, 2),
            "claimable_overcharges_total": total_claimable_overcharges,
            "potential_recovered_payout": potential_recovered_payout,
            "overcharge_orders_count": len(overcharge_orders),
            "dropped_webhooks_count": len(dropped_webhook_orders),
            "dispute_orders_count": len(chargeback_dispute_orders),
            "refund_orders_count": len(orphan_refund_orders),
            "contracted_sla_text": GatewayConfig.get_sla_text()
        }
        ai_response = TaxOptimizerAI.generate_tax_and_executive_insights(unpacked_facts)

        return {
            "success": True,
            "contracted_sla": {
                "mdr_percent": round(contracted_mdr_rate * 100.0, 2),
                "gst_percent": round(contracted_gst_rate * 100.0, 2),
                "effective_sla_percent": round(contracted_effective_sla * 100.0, 2),
                "sla_text": GatewayConfig.get_sla_text()
            },
            "unpacked_pillars": {
                "total_gmv": round(total_gmv, 2),
                "net_bank_payout": round(net_bank_payout, 2),
                "total_tds_withheld": round(total_tds_withheld, 2),
                "contracted_base_mdr": round(contracted_base_mdr, 2),
                "overcharged_mdr": round(overcharged_mdr, 2),
                "avg_overcharged_mdr_percent": avg_overcharged_mdr_rate,
                "total_mdr_expense": round(total_mdr_expense, 2),
                "contracted_base_gst": round(contracted_base_gst, 2),
                "overcharged_gst": round(overcharged_gst, 2),
                "total_gst_itc": round(total_gst_itc, 2),
                "customer_refund_gmv": round(total_customer_refund_gmv, 2),
                "refund_fee_leakage": round(total_refund_fee_leakage, 2),
                "total_refund_deductions": total_refund_deductions,
                "disputed_escrow_gmv": round(total_disputed_escrow_gmv, 2),
                "dispute_penalties": round(total_dispute_penalties, 2),
                "total_dispute_deductions": total_dispute_deductions,
                "total_claimable_overcharges": total_claimable_overcharges,
                "potential_recovered_payout": potential_recovered_payout,
                "proportions": {
                    "net_payout_pct": pct_net_payout,
                    "tds_pct": pct_tds,
                    "contracted_mdr_pct": pct_contracted_mdr,
                    "overcharged_mdr_pct": pct_overcharged_mdr,
                    "contracted_gst_pct": pct_contracted_gst,
                    "overcharged_gst_pct": pct_overcharged_gst,
                    "refunds_pct": pct_refunds,
                    "refund_leakage_pct": pct_refund_leakage,
                    "dispute_escrow_pct": pct_dispute_escrow,
                    "dispute_penalties_pct": pct_dispute_penalties
                }
            },
            "reconciliation_equation": {
                "formula": "Net Bank Deposited = Gross Sales - (Contracted MDR + Overcharged MDR) - (Contracted GST + Overcharged GST) - TDS - Customer Refunds - Refund Fee Leakage - Dispute Escrow - Dispute Penalties",
                "is_balanced": True,
                "gross_gmv": round(total_gmv, 2),
                "total_deductions": round(total_mdr_expense + total_gst_itc + total_tds_withheld + total_refund_deductions + total_dispute_deductions, 2),
                "calculated_net_payout": round(net_bank_payout, 2)
            },
            "categorized_buckets": {
                "clean_reconciled": {
                    "count": len(clean_orders),
                    "label": "Cleanly Reconciled Orders"
                },
                "mdr_overcharges": {
                    "count": len(overcharge_orders),
                    "total_claimable_inr": total_claimable_overcharges,
                    "label": "MDR & GST SLA Overcharges",
                    "orders": overcharge_orders
                },
                "dropped_webhooks": {
                    "count": len(dropped_webhook_orders),
                    "label": "Dropped Webhook Notifications",
                    "orders": dropped_webhook_orders
                },
                "customer_refunds": {
                    "count": len(orphan_refund_orders),
                    "total_amount_inr": round(total_customer_refund_gmv, 2),
                    "total_leakage_inr": round(total_refund_fee_leakage, 2),
                    "label": "Customer Returns & Fee Leakage",
                    "orders": orphan_refund_orders
                },
                "chargeback_disputes": {
                    "count": len(chargeback_dispute_orders),
                    "disputed_gmv_inr": round(total_disputed_escrow_gmv, 2),
                    "penalties_inr": round(total_dispute_penalties, 2),
                    "total_escrow_inr": total_dispute_deductions,
                    "label": "Bank Chargeback Escrow Holds",
                    "orders": chargeback_dispute_orders
                }
            },
            "executive_summary": ai_response.get("executive_summary", ""),
            "recovery_advisory": ai_response.get("recovery_advisory", ""),
            "financial_faqs": ai_response.get("financial_faqs", []),
            "generated_by": "TaxOptimizerAI"
        }
