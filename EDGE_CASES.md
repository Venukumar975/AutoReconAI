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
  A customer returns an item worth ₹1,200 bought during the previous billing cycle. Razorpay processes the refund and automatically deducts ₹1,200 from **today's** aggregate payout.

* **Table State & Discrepancy:**
  * **`orders` table (Today):** Does not contain the original order (it was placed last week).
  * **`payments` table / Bank Deposit:** Total payout is short by **₹1,200.00**.
  * **Discrepancy:** Bank deposit is lower than today's net sales total because an unlinked refund was deducted.

* **AI Finance Controller Action:**
  1. Detects a negative credit transaction (`type: refund`) unlinked to today's order batch.
  2. Classifies anomaly as `ORPHAN_REFUND`.
  3. Adjusts today's settlement calculation and books a double-entry entry to *Prior Period Returns & Allowances* so the day's books balance to the exact paise.

---

## 4. Master Comparison Matrix

| # | Anomaly Name | Where the Issue Appears | Cause | Resolution by AI Finance Controller |
|---|---|---|---|---|
| **1** | **Dropped Webhook** | `orders` = PENDING vs `payments` = captured | Webhook failed / network timeout | Flags ghost payment $\rightarrow$ Recommends auto-fulfillment |
| **2** | **Fee Overcharge** | Razorpay fee > Agreed 2% MDR schedule | Wrong rate tier applied (2.75%) | Calculates ₹ variance $\rightarrow$ Drafts Razorpay dispute ticket |
| **3** | **Orphan Refund** | Bank payout short by ₹1,200 with no order today | Prior-cycle return deducted today | Links refund $\rightarrow$ Books to *Returns Allowed* ledger |

---

## 5. Accounting Formula Reference

### 1. Net Settlement Expectation:
$$\text{Expected Net Credit} = \text{Gross Amount} - \text{MDR Fee} - \text{GST (18\%)}$$

### 2. Fee Variance:
$$\text{Fee Variance} = (\text{Actual Fee} + \text{Actual GST}) - (\text{Contracted Fee} + \text{Contracted GST})$$

### 3. Double-Entry Balanced Ledger Rule:
$$\sum \text{Debits (Bank Deposit + Razorpay Fees + GST)} == \sum \text{Credits (Gross Sales Revenue)}$$
