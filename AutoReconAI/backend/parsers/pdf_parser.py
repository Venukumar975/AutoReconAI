"""
AutoReconAI - Bank Statement PDF Parser
=======================================
Extracts tabular transactions from digital Bank PDFs using pdfplumber.
- Scans all pages and detects the first table having >= 5 columns (skipping small metadata tables).
- Extracts raw headers and preview rows for the interactive user mapping modal.
- Extracts accurate UTR tokens using robust regex.
"""

import pdfplumber
import re
from typing import Dict, List, Tuple, Any


def detect_and_extract_pdf_table(pdf_path: str) -> Tuple[List[str], List[List[str]], List[List[str]], float]:
    """
    Scans the PDF and finds the first table with >= 5 columns.
    Extracts headers, preview rows, data rows, and auto-detected opening balance.
    """
    detected_headers = []
    all_rows = []
    detected_op_bal = 10000.00

    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text() or ""
            full_text += " " + t
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                header_candidate = [c.replace("\n", " ").strip() if c else "" for c in table[0]]
                non_empty_cols = [c for c in header_candidate if c]

                if len(non_empty_cols) >= 5:
                    if not detected_headers:
                        detected_headers = header_candidate
                        for row in table[1:]:
                            clean_row = [c.replace("\n", " ").strip() if c else "" for c in row]
                            if any(clean_row):
                                all_rows.append(clean_row)
                    else:
                        for row in table:
                            clean_row = [c.replace("\n", " ").strip() if c else "" for c in row]
                            if clean_row == detected_headers or clean_row == header_candidate:
                                continue
                            if any(clean_row):
                                all_rows.append(clean_row)

        # Regex scan for Opening Balance in statement text
        op_match = re.search(r'(?:opening\s*balance|op\s*bal|opening\s*bal|b/f\s*balance)\s*[:=]?\s*(?:rs\.?|inr|₹)?\s*([0-9,]+(?:\.[0-9]{1,2})?)', full_text, re.IGNORECASE)
        if op_match:
            try:
                val_str = op_match.group(1).replace(",", "")
                detected_op_bal = round(float(val_str), 2)
            except ValueError:
                pass

    preview_rows = all_rows[:3] if len(all_rows) >= 3 else all_rows
    return detected_headers, preview_rows, all_rows, detected_op_bal


def parse_mapped_pdf_transactions(all_rows: List[List[str]], mapping: Dict[str, str], headers: List[str]) -> List[Dict[str, Any]]:
    """
    Applies user column mapping to convert raw PDF rows into clean standard transactions.
    """
    header_indices = {h: idx for idx, h in enumerate(headers)}

    def get_val(row: List[str], key: str) -> str:
        col_name = mapping.get(key)
        if col_name and col_name in header_indices:
            idx = header_indices[col_name]
            if idx < len(row):
                return row[idx].strip()
        return ""

    transactions = []

    for row_idx, row in enumerate(all_rows, 1):
        date_val = get_val(row, "txn_date") or f"Day-{row_idx}"

        prim_narr = get_val(row, "primary_narration")
        sec_narr = get_val(row, "secondary_narration")
        full_narr = f"{prim_narr} {sec_narr}".strip() if sec_narr else prim_narr

        debit_raw = get_val(row, "debit").replace(",", "").replace("-", "0").replace("INR", "").strip()
        credit_raw = get_val(row, "credit").replace(",", "").replace("-", "0").replace("INR", "").strip()
        balance_raw = get_val(row, "balance").replace(",", "").replace("-", "0").replace("INR", "").strip()

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

        # Match exact settlement UTR token (e.g. CMS202609017536)
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
