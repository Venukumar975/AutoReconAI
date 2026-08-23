"""
AutoReconAI - Backend Application Server
========================================
Runs on port 5055 (http://127.0.0.1:5055).
Serves the Razorpay Blade-styled AutoReconAI frontend and handles:
- Store Orders CSV upload & parsing
- Bank Statement PDF/Excel >= 5 cols table detection & interactive column mapping
- Razorpay Settlement CSV upload & parsing
- Linked Grouped Reconciliation Matrix
"""

import json
import os
import re
import sys
import tempfile
import traceback
from collections import defaultdict
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, CURRENT_DIR)

from parsers.pdf_parser import detect_and_extract_pdf_table, parse_mapped_pdf_transactions
from parsers.excel_parser import detect_and_extract_excel_table, parse_mapped_excel_transactions
from parsers.csv_parser import parse_orders_csv, parse_settlement_csv

STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
PORT = 5055

app = Flask(__name__, static_folder=STATIC_DIR)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

SESSION_DATA = {
    "orders": [],
    "bank_raw_rows": [],
    "bank_headers": [],
    "bank_file_type": None,
    "bank_txns": [],
    "settlements": []
}


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def serve_index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(STATIC_DIR, path)


@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({
        "service": "AutoReconAI Ingestion Hub",
        "status": "online",
        "port": PORT,
        "session_state": {
            "has_orders": len(SESSION_DATA["orders"]) > 0,
            "orders_count": len(SESSION_DATA["orders"]),
            "has_bank_statement": len(SESSION_DATA["bank_txns"]) > 0,
            "bank_txns_count": len(SESSION_DATA["bank_txns"]),
            "has_settlement": len(SESSION_DATA["settlements"]) > 0,
            "settlements_count": len(SESSION_DATA["settlements"])
        }
    })


@app.route("/api/session/reset", methods=["POST"])
def reset_session():
    SESSION_DATA["orders"] = []
    SESSION_DATA["bank_raw_rows"] = []
    SESSION_DATA["bank_headers"] = []
    SESSION_DATA["bank_file_type"] = None
    SESSION_DATA["bank_txns"] = []
    SESSION_DATA["settlements"] = []
    return jsonify({"success": True, "message": "Session reset successfully"})


@app.route("/api/upload/orders", methods=["POST"])
def upload_orders():
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files["file"]
        if not file.filename.endswith(".csv"):
            return jsonify({"success": False, "error": "Please upload a valid CSV file (.csv)"}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        orders = parse_orders_csv(tmp_path)
        os.remove(tmp_path)

        SESSION_DATA["orders"] = orders
        total_gmv = sum(o["gross_amount"] for o in orders)
        fulfilled_count = sum(1 for o in orders if o["order_status"] == "FULFILLED")

        return jsonify({
            "success": True,
            "filename": file.filename,
            "total_orders": len(orders),
            "total_gmv": round(total_gmv, 2),
            "fulfilled_count": fulfilled_count,
            "preview_rows": orders[:5]
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/upload/detect-bank-table", methods=["POST"])
def detect_bank_table():
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files["file"]
        filename = file.filename.lower()

        if not (filename.endswith(".pdf") or filename.endswith(".xlsx") or filename.endswith(".xls")):
            return jsonify({"success": False, "error": "Please upload a digital Bank PDF (.pdf) or Excel (.xlsx) file"}), 400

        suffix = ".pdf" if filename.endswith(".pdf") else ".xlsx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        if suffix == ".pdf":
            headers, preview_rows, all_rows, detected_op_bal = detect_and_extract_pdf_table(tmp_path)
            file_type = "pdf"
        else:
            headers, preview_rows, all_rows, detected_op_bal = detect_and_extract_excel_table(tmp_path)
            file_type = "excel"

        os.remove(tmp_path)

        if not headers or len(headers) < 5:
            return jsonify({
                "success": False,
                "error": "No tabular statement with >= 5 columns found in this file. Please ensure it has standard bank statement table layout."
            }), 400

        SESSION_DATA["bank_headers"] = headers
        SESSION_DATA["bank_raw_rows"] = all_rows
        SESSION_DATA["bank_file_type"] = file_type
        SESSION_DATA["detected_opening_balance"] = detected_op_bal

        suggested_mapping = {
            "txn_date": None,
            "debit": None,
            "credit": None,
            "balance": None,
            "primary_narration": None,
            "secondary_narration": None
        }

        for h in headers:
            h_clean = h.strip()
            h_lower = h_clean.lower()

            if not suggested_mapping["txn_date"] and re.search(r'\b(txn\s*date|transaction\s*date|date|value\s*date)\b', h_lower):
                if "value" not in h_lower or not suggested_mapping["txn_date"]:
                    suggested_mapping["txn_date"] = h_clean

            if not suggested_mapping["primary_narration"] and re.search(r'\b(description|narration|particulars|remarks|details)\b', h_lower):
                suggested_mapping["primary_narration"] = h_clean

            if not suggested_mapping["secondary_narration"] and re.search(r'\b(ref|cheque|chq|reference)\b', h_lower):
                suggested_mapping["secondary_narration"] = h_clean

            if not suggested_mapping["debit"] and re.search(r'\b(debit|withdrawal|dr)\b', h_lower):
                suggested_mapping["debit"] = h_clean

            if not suggested_mapping["credit"] and re.search(r'\b(credit|deposit|cr)\b', h_lower) and "desc" not in h_lower:
                suggested_mapping["credit"] = h_clean

            if not suggested_mapping["balance"] and re.search(r'\b(balance|closing|running)\b', h_lower):
                suggested_mapping["balance"] = h_clean

        return jsonify({
            "success": True,
            "filename": file.filename,
            "file_type": file_type,
            "detected_headers": headers,
            "suggested_mapping": suggested_mapping,
            "preview_rows": preview_rows,
            "total_extracted_rows": len(all_rows),
            "detected_opening_balance": round(detected_op_bal, 2)
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/upload/apply-bank-mapping", methods=["POST"])
def apply_bank_mapping():
    try:
        data = request.get_json(force=True) or {}
        mapping = data.get("mapping", {})
        opening_bal = float(data.get("opening_balance", 10000.00))
        SESSION_DATA["opening_balance"] = opening_bal

        headers = SESSION_DATA["bank_headers"]
        all_rows = SESSION_DATA["bank_raw_rows"]
        file_type = SESSION_DATA["bank_file_type"]

        if not headers or not all_rows:
            return jsonify({"success": False, "error": "No statement data in session. Please upload statement first."}), 400

        if file_type == "pdf":
            txns = parse_mapped_pdf_transactions(all_rows, mapping, headers)
        else:
            txns = parse_mapped_excel_transactions(all_rows, mapping, headers)

        SESSION_DATA["bank_txns"] = txns

        total_credits = sum(t["credit"] for t in txns)
        total_debits = sum(t["debit"] for t in txns)
        gateway_credits_count = sum(1 for t in txns if t["is_gateway_credit"])
        operating_debits_count = sum(1 for t in txns if not t["is_gateway_credit"] and t["debit"] > 0)

        return jsonify({
            "success": True,
            "total_transactions": len(txns),
            "total_credits": round(total_credits, 2),
            "total_debits": round(total_debits, 2),
            "gateway_credits_count": gateway_credits_count,
            "operating_debits_count": operating_debits_count,
            "preview_rows": txns[:5]
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/upload/settlement", methods=["POST"])
def upload_settlement():
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files["file"]
        if not file.filename.endswith(".csv"):
            return jsonify({"success": False, "error": "Please upload a valid CSV file (.csv)"}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        settlements = parse_settlement_csv(tmp_path)
        os.remove(tmp_path)

        SESSION_DATA["settlements"] = settlements
        total_amount = sum(s["amount"] for s in settlements)
        total_fees = sum(s["fee"] for s in settlements)
        total_tax = sum(s["tax"] for s in settlements)
        total_net_credit = sum(s["net_credit"] for s in settlements)

        return jsonify({
            "success": True,
            "filename": file.filename,
            "total_records": len(settlements),
            "total_amount": round(total_amount, 2),
            "total_fees": round(total_fees, 2),
            "total_tax": round(total_tax, 2),
            "total_net_credit": round(total_net_credit, 2),
            "preview_rows": settlements[:5]
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/generate-linked-grid", methods=["GET"])
def generate_linked_grid():
    try:
        orders = SESSION_DATA["orders"]
        bank_txns = SESSION_DATA["bank_txns"]
        settlements = SESSION_DATA["settlements"]

        if not orders or not bank_txns or not settlements:
            return jsonify({
                "success": False,
                "error": "All 3 files (Orders, Bank Statement, and Settlement CSV) must be uploaded before generating the reconciliation matrix."
            }), 400

        orders_by_id = {o["order_id"]: o for o in orders}
        bank_by_utr = {}
        for b in bank_txns:
            if b.get("extracted_utr") and b["extracted_utr"] != "-":
                bank_by_utr[b["extracted_utr"]] = b

        utr_groups_dict = defaultdict(list)
        for s in settlements:
            utr_key = s.get("settlement_utr", "-")
            utr_groups_dict[utr_key].append(s)

        grouped_utr_list = []
        total_gmv = 0.0
        total_fees = 0.0
        total_gst = 0.0
        total_bank_deposited = 0.0
        matched_orders_count = 0
        total_orders_count = 0

        for utr, s_list in utr_groups_dict.items():
            group_gross = sum(s["amount"] for s in s_list)
            group_fee = sum(s["fee"] for s in s_list)
            group_tax = sum(s["tax"] for s in s_list)
            group_net = sum(s["net_credit"] for s in s_list)

            total_gmv += group_gross
            total_fees += group_fee
            total_gst += group_tax

            bank_info = bank_by_utr.get(utr)
            bank_deposited = bank_info["credit"] if bank_info else 0.0
            bank_date = bank_info.get("txn_date", "") if bank_info else "⚠️ Bank Credit Missing"
            if bank_deposited > 0:
                total_bank_deposited += bank_deposited

            child_orders = []

            for s in s_list:
                total_orders_count += 1
                oid = s["order_id"]
                order_info = orders_by_id.get(oid)
                order_status = order_info["order_status"] if order_info else "UNKNOWN"
                
                raw_dt = s.get("created_at") or (order_info.get("created_at") if order_info else "") or ""
                raw_dt_str = str(raw_dt).strip()

                if raw_dt_str:
                    try:
                        dt_obj = re.search(r'(\d{4})-(\d{2})-(\d{2})', raw_dt_str)
                        if dt_obj:
                            months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                            m_name = months[int(dt_obj.group(2)) - 1]
                            formatted_date = f"{dt_obj.group(3)}-{m_name}-{dt_obj.group(1)}"
                        else:
                            formatted_date = raw_dt_str[:10]
                    except Exception:
                        formatted_date = raw_dt_str[:10]
                else:
                    formatted_date = "-"

                # Detect 3 Core Edge Case Mismatches
                fee_rate = (s["fee"] / s["amount"]) if s["amount"] > 0 else 0.0
                is_fee_overcharged = (fee_rate > 0.0205)
                is_webhook_pending = (order_status == "PENDING")
                is_orphan_refund = (oid not in orders_by_id or s["net_credit"] < 0)

                is_mismatched = is_webhook_pending or is_fee_overcharged or is_orphan_refund

                if not is_mismatched and order_status == "FULFILLED":
                    matched_orders_count += 1
                    matched_badge = "✅ Matched"
                    settled_badge = "matched 100%"
                else:
                    matched_badge = "⚠️ Mismatched"
                    settled_badge = "Mismatched"

                child_orders.append({
                    "order_id": oid,
                    "date": formatted_date,
                    "billed": s["amount"],
                    "mdr": s["fee"],
                    "gst": s["tax"],
                    "net_payout": s["net_credit"],
                    "matched": matched_badge,
                    "settled": settled_badge,
                    "order_status": order_status,
                    "is_mismatched": is_mismatched,
                    "is_fee_overcharged": is_fee_overcharged,
                    "is_webhook_pending": is_webhook_pending,
                    "is_orphan_refund": is_orphan_refund
                })

            grouped_utr_list.append({
                "settlement_utr": utr,
                "bank_date": bank_date,
                "bank_deposited": round(bank_deposited, 2),
                "orders": child_orders
            })

        # Sort UTR groups chronologically by date ASC
        def get_utr_sort_key(group):
            orders_list = group.get("orders", [])
            for o in orders_list:
                dt_str = o.get("date", "")
                if dt_str and dt_str != "-":
                    try:
                        parts = dt_str.split("-")
                        if len(parts) == 3 and len(parts[1]) == 3:
                            months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                            m_idx = months.index(parts[1]) + 1 if parts[1] in months else 1
                            return f"{parts[2]}-{m_idx:02d}-{int(parts[0]):02d}"
                    except Exception:
                        pass
                    return dt_str
            return "9999-99-99"

        grouped_utr_list.sort(key=get_utr_sort_key)

        mismatched_count = total_orders_count - matched_orders_count
        match_rate = round((matched_orders_count / max(total_orders_count, 1)) * 100, 1)

        return jsonify({
            "success": True,
            "summary": {
                "total_utr_groups": len(grouped_utr_list),
                "total_gmv": round(total_gmv, 2),
                "total_fees": round(total_fees, 2),
                "total_gst": round(total_gst, 2),
                "total_bank_deposited": round(total_bank_deposited, 2),
                "matched_count": matched_orders_count,
                "mismatched_count": mismatched_count,
                "match_rate": f"{match_rate}%"
            },
            "utr_groups": grouped_utr_list
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)
