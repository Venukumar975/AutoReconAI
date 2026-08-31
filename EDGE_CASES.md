# Financial Reconciliation & Commercial Edge Cases Reference
**Project:** Razorpay AI Finance Controller (Autonome-Recon)  
**Author / Team:** Venukumar975  
**Purpose:** Single source of truth for understanding how database tables behave during shopping scenarios and how the 5 critical commercial edge cases are detected, triaged, and resolved.

---

## 1. The 3-Way Financial Triangulation
In real e-commerce, money moves through three separate systems before landing in the merchant's bank:

```
┌────────────────────────────────┐    ┌─────────────────────────────────┐    ┌────────────────────────────────┐
│      1. Store DB (store.db)    │    │      2. Razorpay Gateway        │    │    3. Bank Statement PDF       │
│  • orders: Master sale bill    │    │  • payments: Gross amount       │    │  • Individual deposit lines    │
│  • cart: Item line breakdown   │    │  • Fee deductions (2% MDR)      │    │  • Bank UTR transaction refs   │
│  • products: Price reference   │    │  • Tax deductions (18% GST)     │    │  • Credit / Debit balance      │
└────────────────────────────────┘    └─────────────────────────────────┘    └────────────────────────────────┘
```

---

## 2. User Shopping Scenarios & Database Table Behaviors

### 🛒 Scenario 1: User Adds Items to Cart but DOES NOT Buy (Abandoned Cart)
* **What Happens:** The customer browses the website, clicks `+ Add to Cart` on products, but never clicks checkout or pays.
* **Database State:**
  * **`cart` table:** Holds the items in the temporary active basket.
  * **`orders` table:** **`0` rows / No record** (Sale was never finalized).
  * **`payments` table:** **`0` rows / No record** (No gateway transaction initiated).
* **Financial Impact:** Zero money moved. No impact on financial books, cash flow, or bank reconciliation.

---

### 💳 Scenario 2: User Adds Items to Cart and BUYS via Razorpay
* **What Happens:** Customer selects items, opens the cart modal, clicks `Buy Now`, and completes payment on Razorpay.
* **Database State (All 3 Tables Updated):**
  1. **`cart` table:** Records each line item with quantity and price, linked to the `order_id` (e.g. `2x Rice @ ₹399 = ₹798`, `1x Atta @ ₹465 = ₹465`).
  2. **`orders` table:** Creates the **Master Store Bill** (`order_id: ORD_1001`, `customer_name: Priya Patel`, `gross_amount: ₹1,263.00`, `order_status: FULFILLED`).
  3. **`payments` table:** Creates the **Gateway Ledger Record** (`payment_id: pay_P1001`, `amount: ₹1,263.00`, `fee: ₹25.26`, `tax: ₹4.55`, `net_credit: ₹1,233.19`, `settlement_utr: CMS9823412098`, `status: captured`).

---

## 3. The 3 Core Commercial Edge Cases (Root Causes & Resolutions)

---

### ⚠️ Edge Case 1: Dropped Webhook (Ghost Payment / Pending Order)

* **Root Cause:**  
  The customer completes payment on Razorpay, and money is deducted from their account. However, due to a temporary network drop, packet loss, or merchant server timeout, Razorpay's webhook fails to reach the store server.

* **Table State & Discrepancy:**
  * **`payments` table:** Shows payment **`captured`** (Razorpay collected ₹3,500.00).
  * **`orders` table:** Order status remains stuck on **`PENDING`** (Store assumes customer cancelled).
  * **Discrepancy:** Gateway has collected funds, but the store has not fulfilled or shipped the order.

* **AI Finance Controller Action:**
  1. Detects `payments.status == 'captured'` while `orders.order_status == 'PENDING'`.
  2. Classifies anomaly as `DROPPED_WEBHOOK`.
  3. Recommends immediate order fulfillment and logs the webhook gap in the audit ledger.

---

### ⚠️ Edge Case 2: Merchant Discount Rate (MDR) Fee Overcharge

* **Root Cause:**  
  The merchant's signed SLA with Razorpay specifies a **2.00% domestic MDR**. Razorpay's billing engine incorrectly applies a **2.75% international card rate** on a domestic transaction.

* **Table State & Discrepancy:**
  * **`orders` table:** Gross Sale = **₹2,500.00**.
  * **Expected Calculation:**
    $$\text{Expected Fee} = 2,500 \times 2.00\% = ₹50.00$$
    $$\text{Expected GST (18\%)} = 50.00 \times 18\% = ₹9.00$$
    $$\text{Total Expected Deduction} = ₹59.00 \implies \text{Net Payout} = ₹2,441.00$$
  * **Actual Razorpay Charge (at 2.75%):**
    $$\text{Actual Fee} = 2,500 \times 2.75\% = ₹68.75$$
    $$\text{Actual GST (18\%)} = 68.75 \times 18\% = ₹12.38$$
    $$\text{Total Actual Deduction} = ₹81.13 \implies \text{Net Payout} = ₹2,418.87$$
  * **Mathematical Variance:** Overcharged by **₹22.13** ($81.13 - 59.00$).

* **AI Finance Controller Action:**
  1. Flagged deterministically by the fee calculator ($|\text{variance}| > ₹0.05$).
  2. Classifies anomaly as `FEE_OVERCHARGE`.
  3. Auto-drafts a formal **Razorpay Merchant Dispute Claim Ticket** with the transaction ID (`pay_...`), gross amount, contracted rate, and claim amount (₹22.13) ready for Razorpay support.

---

### ⚠️ Edge Case 3: Orphan Customer Refund (Prior-Period Deduction)

* **Root Cause:**  
  A customer returns an item worth ₹1,200 bought during the previous billing cycle. Razorpay processes the refund and automatically deducts ₹1,200 from **today's** aggregate payout. Under Razorpay refund policy, the original MDR fee & GST are retained / non-reversed.

* **Table State & Discrepancy:**
  * **`orders` table (Today):** Does not contain the original order (it was placed last week).
  * **`payments` table / Bank Deposit:** Total payout is short by **₹1,200.00** + retained MDR fee loss.
  * **Discrepancy:** Bank deposit is lower than today's net sales total because an unlinked refund was deducted.

* **AI Finance Controller Action:**
  1. Detects a negative credit transaction (`type: refund`) unlinked to today's order batch.
  2. Classifies anomaly as `ORPHAN_REFUND`.
  3. Adjusts today's settlement calculation and books a double-entry entry to *Prior Period Returns & Allowances* so the day's books balance to the exact paise.

---

### ⚠️ Edge Case 4: Customer Bank Chargeback & Dispute Fee Hold

* **Root Cause:**  
  A customer raises a fraud dispute directly with their issuing bank (e.g. SBI/HDFC). Razorpay forcefully holds/debits the full transaction amount from today's settlement payout and slaps a mandatory administrative **Dispute Fee** (₹500.00 + 18% GST = ₹590.00) on the merchant.

* **Table State & Discrepancy:**
  * **`orders` table:** Order status remains **`FULFILLED`** (store packaged and shipped the goods).
  * **`payments` table:** Records a debit transaction with `status: dispute_hold`, `amount: ₹2,500.00`, `fee: ₹500.00`, `tax: ₹90.00`, and `net_credit: -₹3,090.00`.
  * **Discrepancy:** Today's bank deposit is short by ₹3,090.00 despite the store order being fully fulfilled.

* **AI Finance Controller Action:**
  1. Identifies the record as `CHARGEBACK_DISPUTE_HOLD`.
  2. Allocates ₹590.00 to *Dispute Handling Expense* and moves ₹2,500.00 to *Escrow Reserve Hold*.
  3. Auto-drafts a **Chargeback Evidence Defense Kit** (with delivery AWB, invoice, and OTP logs) for Razorpay Support to contest the chargeback within the 7-day SLA window.

---

### ⚠️ Edge Case 5: Section 194-O Statutory 1% TDS Upfront Deduction

* **Root Cause:**  
  Under Section 194-O of the Indian Income Tax Act, payment gateways are legally mandated to deduct **1.00% TDS** on gross e-commerce sales value before releasing payout to the merchant.

* **Table State & Discrepancy:**
  * **`orders` table:** Gross Sale = **₹10,000.00**.
  * **Deductions:**
    - 2.00% Domestic MDR = ₹200.00
    - 18.00% GST on MDR = ₹36.00
    - **1.00% Section 194-O TDS** = ₹100.00 (Deposited to Govt against merchant's PAN)
  * **Net Bank Payout:** **₹9,664.00** (instead of ₹9,764.00).
  * **Discrepancy:** Bank payout has a 1% shortfall compared to the basic $(Gross - MDR - GST)$ formula.

* **AI Finance Controller Action:**
  1. Detects exact 1.00% statutory withholding on gross amount.
  2. Classifies anomaly as `STATUTORY_SECTION_194O_TDS`.
  3. Avoids raising false MDR overcharge dispute tickets against Razorpay.
  4. Automatically routes the ₹100.00 deduction to the *TDS Receivable (Form 26AS / Advance Income Tax Asset)* ledger for end-of-year tax returns.

---

## 4. Master Comparison Matrix

| # | Anomaly Name | Where the Issue Appears | Cause | Resolution by AI Finance Controller |
|---|---|---|---|---|
| **1** | **Dropped Webhook** | `orders` = PENDING vs `payments` = captured | Webhook failed / network timeout | Flags ghost payment $\rightarrow$ Recommends auto-fulfillment |
| **2** | **Fee Overcharge** | Razorpay fee > Agreed 2% MDR schedule | Wrong rate tier applied (2.75%) | Calculates ₹ variance $\rightarrow$ Drafts Razorpay dispute ticket |
| **3** | **Orphan Refund** | Bank payout short by ₹1,200 with no order today | Prior-cycle return deducted today | Links refund $\rightarrow$ Books to *Returns Allowed* ledger |
| **4** | **Bank Chargeback** | Store `FULFILLED` vs Gateway `dispute_hold` debit | Customer disputed charge with bank | Isolates ₹590 fee loss $\rightarrow$ Auto-drafts Proof of Delivery Defense Kit |
| **5** | **Sec 194-O TDS** | Bank payout short by exact 1% of Gross Sale | Mandatory Income Tax deduction | Validates 1% $\rightarrow$ Maps to *Form 26AS Tax Asset* ledger |

---

## 5. Accounting Formula Reference

### 1. Standard Net Settlement (No TDS):
$$\text{Expected Net Credit} = \text{Gross Amount} - \text{MDR Fee} - \text{GST (18\%)}$$

### 2. Statutory Net Settlement (With Section 194-O TDS):
$$\text{Expected Net Credit} = \text{Gross Amount} - \text{MDR Fee} - \text{GST (18\%)} - (\text{Gross Amount} \times 1.00\% \text{ TDS})$$

### 3. Chargeback Debit Settlement:
$$\text{Net Chargeback Debit} = -(\text{Disputed Order Amount} + \text{Dispute Fee (₹500)} + \text{GST (18\%) (₹90)})$$

### 4. Fee Variance:
$$\text{Fee Variance} = (\text{Actual Fee} + \text{Actual GST}) - (\text{Contracted Fee} + \text{Contracted GST})$$

