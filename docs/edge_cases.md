# Financial Reconciliation & Commercial Edge Cases Reference
**Project:** Razorpay AI Finance Controller (AutoReconAI)  
**Author / Team:** Venukumar975  
**Purpose:** Single source of truth for understanding how database tables behave during customer shopping scenarios and why catching these 5 edge cases matters to a real merchant.

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
* **What Happens:** The customer browses the grocery store, clicks `+ Add to Cart` on products, but leaves the website without checking out.
* **Database State:**
  * **`cart` table:** Holds the items in the temporary active basket (`order_id: 'ACTIVE_CART'`).
  * **`orders` table:** **`0` rows / No record** (Sale was never finalized).
  * **`payments` table:** **`0` rows / No record** (No payment was initiated).
* **Financial Impact:** Zero money moved. No impact on bank accounts or accounts books.

---

### 💳 Scenario 2: Completed Checkout via Razorpay Gateway
* **What Happens:** Customer selects items, clicks `Buy Now`, and completes payment on Razorpay.
* **Database State (Triangulated Across Tables):**
  1. **`cart` table:** Records each line item with quantity and price (`2x Rice @ ₹399 = ₹798`, `1x Atta @ ₹465 = ₹465`).
  2. **`orders` table:** Creates the **Store Order** (`order_id: ORD_1001`, `customer_name: Priya Patel`, `gross_amount: ₹1,263.00`, `order_status: FULFILLED`).
  3. **`payments` table:** Creates the **Gateway Ledger Record** (`payment_id: pay_P1001_A8B9C1`, `amount: ₹1,263.00`, `fee: ₹25.26`, `tax: ₹4.55`, `net_credit: ₹1,233.19`, `settlement_utr: CMS202605011029`, `status: captured`).
  4. **Bank Statement:** Net payout arrives in the merchant's bank account under the daily settlement UTR batch.

---

## 3. The 5 Core Commercial Edge Cases (Why They Happen & Real-World Impact)

> 💡 **Important Engineering Context:**  
> In production environments, payment gateways like Razorpay have robust, highly reliable infrastructure. Webhooks utilize asynchronous retry queues with exponential backoff, and gateways do not arbitrarily charge higher MDR rates. However, in large-scale distributed systems under peak concurrency, network timeouts, temporary packet loss, or automated card tier misclassifications can occasionally occur.  
> Because this is a demonstration project exploring how **Agentic AI investigates financial discrepancies**, we simulate these real-world failure modes within a **controlled, parameter-driven environment** (`config.ini`) to give the AI copilot meaningful, verifiable financial anomalies to triage and resolve.

---

### ⚠️ Edge Case 1: Dropped Webhook (Ghost Payment / Pending Order)

* **What Actually Happens:**  
  The customer pays for the order, and Razorpay successfully collects the money and sends it to the merchant's bank account. But during the payment, the network drops for a second, so Razorpay's confirmation message (webhook) never reaches the store website. As a result, the store website still thinks the customer abandoned checkout, leaving the order stuck on **`PENDING`**.

* **Why This Hurts the Business in Real Life:**
  1. **Customer Never Gets Their Package:** Because the store dashboard shows `PENDING`, the warehouse staff assumes payment failed and never packs the goods. Meanwhile, the customer already saw money deducted from their account, leading to angry support calls and bad reviews.
  2. **Accounting Tax Headache (Sales Register & GSTR-1):** When filing monthly sales tax (GSTR-1), the merchant's store records show lower sales than the actual money deposited in the bank account. If the tax department sees more money in your bank than what you reported selling, it triggers tax notices for under-reporting income.
  3. **Exhausting Manual Checks:** Finance teams have to sit with spreadsheets and match thousands of pending orders line-by-line against bank statements just to see who actually paid.

* **How AutoReconAI Fixes It:**  
  The AI traces the order ID, sees that the payment was captured and already deposited into the bank under a verified UTR, and immediately tells the merchant: *"Payment is safe in your bank account—fulfill and ship this order now."*

---

### ⚠️ Edge Case 2: Fee Overcharges (MDR Rate Glitches)

* **What Actually Happens:**  
  When signing up with Razorpay, the merchant agreed to a **2.0% fee**. But due to a system misclassification (like treating a normal domestic debit card as an expensive international credit card), the gateway accidentally charges **2.75%** on some transactions.

* **Why This Hurts the Business in Real Life:**
  1. **Quietly Drains Profit Margins:** E-commerce stores often make only a 5% to 10% profit margin. A silent 0.75% extra fee on thousands of orders eats up a huge portion of the business's actual profit.
  2. **Messing Up GST Tax Credits (Input Tax Credit):** Razorpay charges 18% GST on top of its fee. If the merchant has a GST number, they can claim that 18% GST back from the government when filing monthly GST returns (GSTR-3B). When the gateway overcharges fees, it also overcharges the GST, messing up the merchant's tax credit calculations.
  3. **Hidden Inside Lump-Sum Payouts:** Razorpay doesn't send money order-by-order; it bundles hundreds of orders into one single bank deposit. Finding out that an individual order was charged 2.75% instead of 2.0% is nearly impossible to spot manually in a spreadsheet.

* **How AutoReconAI Fixes It:**  
  The AI uses deterministic Python tools to recalculate every fee against the contracted 2% SLA, calculates the exact extra paise charged, and drafts a ready-to-send dispute ticket to Razorpay support with UTR evidence to get the money refunded.

---

### ⚠️ Edge Case 3: Orphan Customer Refunds (Returns from Last Month)

* **What Actually Happens:**  
  A customer returns an item they bought 30 days ago. The merchant has a customer-friendly policy to give a 100% full refund for damaged or delayed goods. Razorpay processes the refund and deducts that amount directly from **today's** net bank payout.

* **Why This Hurts the Business in Real Life:**
  1. **False "Missing Money" Panic:** The accountant downloads today's store sales report and sees ₹50,000 in sales. But the bank deposit only shows ₹40,000. The accountant panics thinking ₹10,000 went missing, because that old return doesn't exist anywhere in today's sales file.
  2. **Permanent Fee Loss (Sunk Fee Leakage):** Even though the customer got their full money back, Razorpay does NOT refund the original 2% processing fee or the 18% GST that was charged when the customer first bought the item. The merchant permanently absorbs that fee loss.

* **How AutoReconAI Fixes It:**  
  The AI traces the return back to the original order ID from the previous month, explains to the accountant exactly why today's bank payout is lower, and calculates the exact lost processing fees so they can be properly booked as a business return loss instead of an unexplained discrepancy.

---

### ⚠️ Edge Case 4: Customer Disputes & Chargeback Holds

* **What Actually Happens:**  
  A customer calls their bank and says: *"I don't recognize this charge on my credit card"* or *"I never received my delivery."* The bank immediately forces Razorpay to freeze that order's money in escrow, and the gateway slaps an extra administrative dispute penalty (assumed as ₹500 fee + ₹90 GST) onto the merchant.

* **Why This Hurts the Business in Real Life:**
  1. **Strict 7-Day Countdown:** The bank gives the merchant a strict 7-day window to prove the customer actually received the product. If the merchant misses this 7-day deadline, they lose both the product and the money permanently.
  2. **Buried in Bank Statements:** Because dispute deductions are lumped inside the daily settlement payout, merchants often don't notice the chargeback until weeks later—well after the 7-day contest window has already expired!
  3. **Double Financial Hit:** The merchant loses the gross sale amount into an escrow hold, PLUS they immediately lose the ₹590 dispute penalty fee.

* **How AutoReconAI Fixes It:**  
  The AI instantly isolates chargeback holds, flags the active 7-day countdown, and prepares a dispute defense packet (with order details, invoice, and tracking logs) so the merchant can contest the chargeback before the deadline runs out.

---

### ⚠️ Edge Case 5: Section 194-O Statutory TDS (Tax Deduction, Not a Bug!)

* **What Actually Happens:**  
  Under Indian tax law (Section 194-O), payment gateways are legally required to deduct a small tax amount (set to a 1% demonstration rate in our config) before releasing payouts to the merchant's bank account. Razorpay deposits this tax directly with the government under the merchant's PAN number.

* **Why This Matters to the Business in Real Life:**
  1. **Not a System Error:** This is not a fee overcharge or missing money. It is standard government advance income tax.
  2. **Prevents False Dispute Tickets:** Accountants who don't understand payment gateway tax rules often assume the gateway stole 1% of their revenue and raise false dispute tickets.
  3. **Claiming It Back in Form 26AS:** At the end of the financial year, the merchant can claim this deducted 1% back against their corporate income tax return by cross-checking their annual **Form 26AS** tax credit statement.

* **How AutoReconAI Fixes It:**  
  The AI verifies that the 1% deduction matches the statutory formula, avoids raising false dispute alarms, and properly maps the deduction to the merchant's Advance Tax Asset ledger so it can be claimed back at tax time.

---

## 4. Master Comparison Matrix across all 5 Edge Cases

| # | Anomaly Name | Where the Issue Appears | Cause | Recoverable? | Resolution by AI Finance Controller |
|:---|:---|:---|:---|:---|:---|
| **1** | **Dropped Webhook** | Store says `PENDING`, but Bank has the money | Network glitch during checkout | Safe (₹0 loss) | Confirms bank deposit $\rightarrow$ Tells store to fulfill and ship order |
| **2** | **Fee Overcharge** | Gateway fee is higher than agreed 2% SLA | System misclassification (2.75%) | **100% Cash** | Calculates exact variance $\rightarrow$ Drafts dispute ticket to Razorpay |
| **3** | **Orphan Refund** | Bank payout is lower, but no return in today's store file | Return from a previous month | **Sunk Fee Loss** | Traces old order $\rightarrow$ Explains payout drop and logs non-refundable fee |
| **4** | **Bank Chargeback** | Store shipped order, but gateway froze funds | Customer disputed charge with bank | **Via Evidence** | Alerts on 7-day deadline $\rightarrow$ Prepares Proof of Delivery Defense Kit |
| **5** | **Sec 194-O TDS** | Bank payout short by exactly 1% of Gross Sale | Government mandatory tax rule | **Tax Credit** | Verifies tax math $\rightarrow$ Books deduction to Form 26AS tax credit ledger |

---

## 5. Master Settlement Balance Equation
To ensure 100% financial integrity, AutoReconAI verifies that every single rupee is accounted for using this live master equation:

$$\text{Net Bank Credit} = \text{Gross Sales (GMV)} - (\text{Contracted MDR} + \text{Overcharged MDR}) - (\text{Contracted GST} + \text{Overcharged GST}) - \text{Statutory TDS} - (\text{Customer Refunds} + \text{Refund Fee Leakage}) - \text{Dispute Escrows} - \text{Dispute Penalties}$$
