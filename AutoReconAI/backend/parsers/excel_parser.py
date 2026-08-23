"""
AutoReconAI - Bank Statement Excel Parser
=========================================
Extracts tabular transactions from Bank Excel files (.xlsx / .xls).
- Detects the table header row having >= 5 columns.
- Extracts accurate UTR tokens using robust regex.
"""

import openpyxl
import re
from typing import Dict, List, Tuple, Any


def detect_and_extract_excel_table(excel_path: str) -> Tuple[List[str], List[List[str]], List[List[str]], float]:
    """
    Scans the active worksheet and finds the header row with >= 5 non-empty columns.
    Returns (headers, preview_rows, all_data_rows, detected_opening_balance).
    """
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb.active

    detected_headers = []
    all_rows = []
    header_row_idx = None
    detected_op_bal = 10000.00

    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        clean_row = [str(c).strip() if c is not None else "" for c in row]
        non_empty = [c for c in clean_row if c]
        row_str = " ".join(non_empty)

        # Check for Opening Balance text in worksheet header rows
        if detected_op_bal == 10000.00:
            op_match = re.search(r'(?:opening\s*balance|op\s*bal|opening\s*bal|b/f\s*balance)\s*[:=]?\s*(?:rs\.?|inr|₹)?\s*([0-9,]+(?:\.[0-9]{1,2})?)', row_str, re.IGNORECASE)
            if op_match:
                try:
                    val_str = op_match.group(1).replace(",", "")
                    detected_op_bal = round(float(val_str), 2)
                except ValueError:
                    pass

        if not detected_headers and len(non_empty) >= 5:
            detected_headers = clean_row
            header_row_idx = row_idx
        elif detected_headers and row_idx > header_row_idx:
            if any(clean_row):
                all_rows.append(clean_row)

    wb.close()
    preview_rows = all_rows[:3] if len(all_rows) >= 3 else all_rows
    return detected_headers, preview_rows, all_rows, detected_op_bal


def parse_mapped_excel_transactions(all_rows: List[List[str]], mapping: Dict[str, str], headers: List[str]) -> List[Dict[str, Any]]:
    """
    Applies user column mapping to convert raw Excel rows into clean standard transactions.
    """
    header_indices = {h: idx for idx, h in enumerate(headers)}

    def get_val(row: List[str], key: str) -> str:
        col_name = mapping.get(key)
        if col_name and col_name in header_indices:
            idx = header_indices[col_name]
            if idx < len(row):
                return str(row[idx]).strip()
        return ""

    transactions = []

    for row_idx, row in enumerate(all_rows, 1):
        date_val = get_val(row, "txn_date") or f"Day-{row_idx}"

        prim_narr = get_val(row, "primary_narration")
        sec_narr = get_val(row, "secondary_narration")
        full_narr = f"{prim_narr} {sec_narr}".strip() if sec_narr else prim_narr

        debit_raw = get_val(row, "debit").replace(",", "").replace("-", "0").replace("None", "0").strip()
        credit_raw = get_val(row, "credit").replace(",", "").replace("-", "0").replace("None", "0").strip()
        balance_raw = get_val(row, "balance").replace(",", "").replace("-", "0").replace("None", "0").strip()

        try:
            debit_amt = float(debit_raw) if debit_raw else 0.0
        except ValueError:
            debit_amt = 0.0

        try:
            credit_amt = float(credit_raw) if credit_raw else 0.0
        except ValueError:
            credit_amt = 0.0

        try:
            balance_amt = float(balance_raw) if balance_raw else 0.0
        except ValueError:
            balance_amt = 0.0

        # Match exact settlement UTR token
        utr_matches = re.findall(r'CMS[0-9]{8,14}|NEFT[0-9A-Za-z]{8,16}|CMS[A-Za-z0-9_]{10,20}', full_narr)
        if utr_matches:
            extracted_utr = utr_matches[-1]
        else:
            fallback = re.search(r'(SETL_[A-Za-z0-9_]+|CMS\w+)', full_narr)
            extracted_utr = fallback.group(1) if fallback else "-"

        transactions.append({
            "txn_date": date_val,
            "description": full_narr or "Bank Transaction",
            "extracted_utr": extracted_utr,
            "debit": debit_amt,
            "credit": credit_amt,
            "balance": balance_amt,
            "is_gateway_credit": "CMS/RAZORPAY" in full_narr.upper() or "RAZORPAY" in full_narr.upper()
        })

    return transactions
