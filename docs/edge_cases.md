# Financial Reconciliation & Commercial Edge Cases Reference
**Project:** Razorpay AI Finance Controller (AutoReconAI)  
**Author / Team:** Venukumar975  
**Purpose:** Single source of truth for understanding how database tables behave during customer shopping scenarios and how the 5 critical commercial edge cases are simulated, detected, triaged, and resolved by the AI Finance Controller.

---

## 1. The 3-Way Financial Triangulation
In real-world e-commerce, money moves across three separate systems before landing in the merchant's bank account:

```
┌────────────────────────────────┐    ┌─────────────────────────────────┐    ┌────────────────────────────────┐
│    1. Merchant Store (5050)    │    │   2. Razorpay Gateway (5051)    │    │    3. Bank Statement (PDF/XLS) │
│  • store_orders.csv / store.db │    │  • razorpay_settlement_recon.csv│    │  • bank_statement_*.pdf/.xlsx  │
│  • Gross Sale Value (GMV)      │    │  • MDR Fee Deductions (e.g. 2%) │    │  • Aggregated Payout Credits   │
│  • Itemized Cart Line Items    │    │  • 18% GST on MDR               │    │  • Bank Settlement UTRs        │
│  • Order Status (FULFILLED)    │    │  • Section 194-O TDS (1.00%)    │    │  • Operating Debits / Expenses │
└────────────────────────────────┘    └─────────────────────────────────┘    └────────────────────────────────┘
```

---

## 2. Customer Shopping Scenarios & Database Table Behaviors (`store.db`)

### 🛒 Scenario 1: Cart Abandonment (Browsing Without Buying)
* **What Happens:** The customer browses the grocery store, clicks `+ Add to Cart` on products, but never clicks checkout or initiates payment.
* **Database State:**
  * **`cart` table:** Holds the items in the temporary active basket (`order_id: 'ACTIVE_CART'`).
  * **`orders` table:** **`0` rows / No record** (Sale was never finalized).
  * **`payments` table:** **`0` rows / No record** (No gateway transaction initiated).
* **Financial Impact:** Zero money moved. No impact on financial books, cash flow, or bank reconciliation.

---

### 💳 Scenario 2: Completed Checkout via Razorpay Gateway
* **What Happens:** Customer selects items, opens the cart modal, clicks `Buy Now`, and completes payment on Razorpay.
* **Database State (Triangulated Across Tables):**
  1. **`cart` table:** Records each line item with quantity and price, linked to the `order_id` (e.g. `2x Rice @ ₹399 = ₹798`, `1x Atta @ ₹465 = ₹465`).
  2. **`orders` table:** Creates the **Master Store Bill** (`order_id: ORD_1001`, `customer_name: Priya Patel`, `gross_amount: ₹1,263.00`, `order_status: FULFILLED`).
  3. **`payments` table:** Creates the **Gateway Ledger Record** (`payment_id: pay_P1001_A8B9C1`, `amount: ₹1,263.00`, `fee: ₹25.26`, `tax: ₹4.55`, `net_credit: ₹1,233.19`, `settlement_utr: CMS202605011029`, `status: captured`).
  4. **Bank Statement:** Net payout credited as part of the daily settlement UTR batch.

---

## 3. The 5 Core Commercial Edge Cases (Root Causes, Simulation & Resolutions)

---

### ⚠️ Edge Case 1: Dropped Webhook (Ghost Payment / Pending Order)

* **Real-World Root Cause:**  
  The customer completes payment on Razorpay, and money is deducted from their account. However, due to a temporary network drop, packet loss, or merchant server timeout, Razorpay's webhook fails to reach the store server (`504 Gateway Timeout`). The store software assumes the customer cancelled checkout.

* **Simulation Implementation:**  
  `Data Simulator & Generator/edge_case_simulators/simulate_dropped_webhooks.py` randomly selects $N$ captured orders in `store.db` and mutates `orders.order_status = 'PENDING'` while `payments.status = 'captured'`.

* **Table State & Discrepancy:**
  * **`orders` table (`store_orders.csv`):** Order status remains stuck on **`PENDING`**.
  * **`payments` table (`razorpay_settlement_recon.csv`):** Shows payment **`captured`** (Razorpay collected funds).
  * **Bank Statement:** Money deposited into merchant bank account under batch UTR.
  * **Discrepancy:** Gateway collected funds and bank received payout, but the store has not fulfilled or shipped the customer order.

* **AI Finance Controller Action:**
  1. Detects `payments.status == 'captured'` while `orders.order_status == 'PENDING'`.
  2. Classifies anomaly as `DROPPED_WEBHOOK`.
  3. Confirms bank deposit is safe $\rightarrow$ Recommends immediate order fulfillment and updates order to `FULFILLED`.

---

### ⚠️ Edge Case 2: Merchant Discount Rate (MDR) Fee Overcharge

* **Real-World Root Cause:**  
  The merchant's signed SLA with Razorpay specifies a **2.00% domestic MDR**. Razorpay's billing engine incorrectly applies a **2.75% international card rate** on a domestic transaction due to tier misclassification.

* **Simulation Implementation:**  
  `Data Simulator & Generator/edge_case_simulators/simulate_fee_overcharges.py` bills $N$ payments at inflated rates (e.g. 2.65% to 2.85% MDR) directly in `payments` table.

* **Table State & Discrepancy (Sample ₹2,500.00 Order):**
  * **Expected Calculation (2.00% MDR + 18.00% GST = 2.36% SLA):**
    $$\text{Expected Fee} = 2,500 \times 2.00\% = ₹50.00$$
    $$\text{Expected GST (18\%)} = 50.00 \times 18\% = ₹9.00$$
    $$\text{Total Expected Deduction} = ₹59.00 \implies \text{Net Payout} = ₹2,441.00$$
  * **Actual Razorpay Charge (at 2.75% MDR + 18.00% GST):**
    $$\text{Actual Fee} = 2,500 \times 2.75\% = ₹68.75$$
    $$\text{Actual GST (18\%)} = 68.75 \times 18\% = ₹12.38$$
    $$\text{Total Actual Deduction} = ₹81.13 \implies \text{Net Payout} = ₹2,418.87$$
  * **Mathematical Variance:** Overcharged by **₹22.13** ($81.13 - 59.00$).

* **AI Finance Controller Action:**
  1. Flagged deterministically by `calculate_fee_discrepancies()` when fee rate exceeds SLA threshold in `config.ini`.
  2. Classifies anomaly as `FEE_OVERCHARGE`.
  3. Auto-drafts a formal **Razorpay Merchant Dispute Claim Ticket** with transaction ID (`pay_...`), gross amount, contracted rate, and exact claim amount (₹22.13) ready for Razorpay support.

---

### ⚠️ Edge Case 3: Orphan Customer Refund & Non-Reversed Fee Leakage

* **Real-World Root Cause:**  
  A customer returns an item worth ₹1,200 bought during the previous billing cycle. Razorpay processes the refund and automatically deducts ₹1,200 from **today's** aggregate payout. Under Razorpay refund policy, the original MDR fee & GST charged on payment capture are **permanently retained / non-reversed**.

* **Simulation Implementation:**  
  `Data Simulator & Generator/edge_case_simulators/simulate_non_reversed_refunds.py` generates dynamic refund records (`ORD_PRIOR_901`) with negative net credits and calculates exact unreversed fee losses.

* **Table State & Discrepancy:**
  * **`orders` table (Today):** Does not contain the original order (it was placed last week).
  * **`payments` table / Bank Deposit:** Total payout is short by **₹1,200.00** + retained MDR fee loss.
  * **Discrepancy:** Bank deposit is lower than today's net sales total because an unlinked prior-period refund was deducted.

* **AI Finance Controller Action:**
  1. `calculate_refund_fee_leakage()` isolates customer returns and quantifies unrecoverable processing loss.
  2. Classifies anomaly as `ORPHAN_REFUND`.
  3. Suppresses false dispute alarms against Razorpay.
  4. Adjusts today's settlement calculation and books a double-entry entry to *Prior Period Returns & Allowances* so the books balance to the exact paise.

---

### ⚠️ Edge Case 4: Customer Bank Chargeback & Dispute Fee Hold

* **Real-World Root Cause:**  
  A customer raises a fraud dispute directly with their issuing bank (e.g. SBI/HDFC/Visa). Razorpay forcefully holds/debits the full transaction amount from today's settlement payout and slaps a mandatory administrative **Dispute Fee** (₹500.00 + 18% GST = ₹590.00) on the merchant.

* **Simulation Implementation:**  
  `Data Simulator & Generator/edge_case_simulators/simulate_chargebacks.py` inserts dispute hold records (`disp_D1001`) with `status: dispute_hold`, ₹500 fee, ₹90 GST, and negative net credits into the same daily settlement UTR batch.

* **Table State & Discrepancy (Sample ₹2,500.00 Disputed Order):**
  * **`orders` table:** Order status remains **`FULFILLED`** (store packaged and shipped the goods).
  * **`payments` table:** Records a debit transaction with `status: dispute_hold`, `amount: ₹2,500.00`, `fee: ₹500.00`, `tax: ₹90.00`, and `net_credit: -₹3,090.00`.
  * **Discrepancy:** Today's bank deposit is short by ₹3,090.00 despite the store order being fully fulfilled.

* **AI Finance Controller Action:**
  1. Identifies the record via `audit_chargeback_holds()`.
  2. Classifies anomaly as `CHARGEBACK_DISPUTE_HOLD`.
  3. Allocates ₹590.00 to *Dispute Handling Expense* and moves ₹2,500.00 to *Escrow Reserve Hold*.
  4. Auto-drafts a **Chargeback Evidence Defense Kit** (with courier AWB tracking, invoice, and delivery logs) for Razorpay Support to contest the chargeback within the mandatory 7-day SLA window.

---

### ⚠️ Edge Case 5: Section 194-O Statutory 1.00% TDS Upfront Deduction

* **Real-World Root Cause:**  
  Under Section 194-O of the Indian Income Tax Act, 1961, payment gateways are legally mandated to deduct **1.00% TDS** on gross e-commerce sales value before releasing payout to the merchant.

* **Simulation Implementation:**  
  `Data Simulator & Generator/edge_case_simulators/simulate_section_194o_tds.py` reads `is_tds_applicable` and `tds_rate_percent` from `config.ini` and applies 1% TDS on captured transactions, updating the `tds` and `net_credit` columns in `payments` table.

* **Table State & Discrepancy (Sample ₹10,000.00 Gross Sales):**
  * **`orders` table:** Gross Sale = **₹10,000.00**.
  * **Deductions:**
    - 2.00% Domestic MDR = ₹200.00
    - 18.00% GST on MDR = ₹36.00
    - **1.00% Section 194-O TDS** = ₹100.00 (Deposited to Govt against merchant's PAN)
  * **Net Bank Payout:** **₹9,664.00** (instead of ₹9,764.00).
  * **Discrepancy:** Bank payout has a 1% shortfall compared to the standard (Gross - MDR - GST) formula.

* **AI Finance Controller Action:**
  1. Detects exact 1.00% statutory withholding on gross amount via `audit_tax_and_tds_deductions()`.
  2. Classifies anomaly as `STATUTORY_SECTION_194O_TDS`.
  3. Avoids raising false MDR overcharge dispute tickets against Razorpay.
  4. Automatically routes the ₹100.00 deduction to the *TDS Receivable (Form 26AS / Advance Income Tax Asset)* ledger for end-of-year tax returns.

---

## 4. Master Comparison Matrix across all 5 Edge Cases

| # | Anomaly Name | Where the Issue Appears | Cause | Recoverable? | Resolution by AI Finance Controller |
|:---|:---|:---|:---|:---|:---|
| **1** | **Dropped Webhook** | `orders` = PENDING vs `payments` = captured | Webhook failed / network timeout | Safe (₹0 loss) | Flags ghost payment $\rightarrow$ Recommends auto-fulfillment |
| **2** | **Fee Overcharge** | Razorpay fee > Agreed 2% MDR schedule | Wrong rate tier applied (2.75%) | **100% Cash** | Calculates ₹ variance $\rightarrow$ Drafts Razorpay dispute ticket |
| **3** | **Orphan Refund** | Bank payout short by ₹1,200 with no order today | Prior-cycle return deducted today | **Sunk Fee Loss** | Quantifies fee leakage $\rightarrow$ Books to *Returns Allowed* ledger |
| **4** | **Bank Chargeback** | Store `FULFILLED` vs Gateway `dispute_hold` debit | Customer disputed charge with bank | **Via Evidence** | Isolates ₹590 fee loss $\rightarrow$ Auto-drafts Proof of Delivery Defense Kit |
| **5** | **Sec 194-O TDS** | Bank payout short by exact 1% of Gross Sale | Mandatory Income Tax deduction | **Tax Asset Credit** | Validates 1% $\rightarrow$ Maps to *Form 26AS Tax Asset* ledger |

---

## 5. Accounting Formula Reference

### 1. Standard Net Settlement (No TDS):
$$\text{Expected Net Credit} = \text{Gross Amount} - \text{MDR Fee} - \text{GST (18\% on MDR)}$$

### 2. Statutory Net Settlement (With Section 194-O TDS):
$$\text{Expected Net Credit} = \text{Gross Amount} - \text{MDR Fee} - \text{GST (18\% on MDR)} - (\text{Gross Amount} \times 1.00\% \text{ TDS})$$

### 3. Chargeback Debit Settlement:
$$\text{Net Chargeback Debit} = -(\text{Disputed Order Amount} + \text{Dispute Fee (₹500.00)} + \text{GST (18\%) (₹90.00)})$$

### 4. Fee Variance:
$$\text{Fee Variance} = (\text{Actual Fee} + \text{Actual GST}) - (\text{Contracted Fee} + \text{Contracted GST})$$

### 5. Non-Reversed Customer Refund Fee Leakage:
$$\text{Un-Reversed Processing Loss} = \text{Retained MDR Fee} + \text{Retained GST (18\%) (Non-Refundable per Gateway Terms)}$$
