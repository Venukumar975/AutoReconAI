# ⚙️ Configuration Guide (`config.ini` & `ai_models.ini`)

AutoReconAI is fully parameter-driven through two dedicated configuration files:
1. **[`config.ini`](../config.ini):** Controls data simulation, transaction volumes, date windows, operational bank expenses, agreed merchant SLA rates, statutory tax profiles, and the 5 prototypic commercial edge cases.
2. **[`ai_models.ini`](../ai_models.ini):** Controls the Google Gemini LLM configuration, temperature, token limits, and multi-tier model fallback chain.

---

## 1. Simulation & Commercial Configuration (`config.ini`)

The simulation settings in `config.ini` are split into two logical sections:

### Section A: Baseline Simulation & Commercial Rates

```ini
[SIMULATION]
simulation_mode = super_fast
razorpay_transactions_count = 60
start_date = 2026-05-01
end_date = 2026-05-30
imputed_expenses_percentage = 20
bank_pdf_format = UNION_BANK
opening_balance = 25000.00

[CONTRACTED_RATES]
mdr_rate_percent = 2.0
gst_rate_percent = 18.0

[MERCHANT_TAX_PROFILE]
gstin = 36AATUF1234F1ZV
pan = ABCDE1234F
is_tds_applicable = yes
tds_rate_percent = 1
```

* **`simulation_mode`**: Selects execution engine — `super_fast` (pure Python HTTP API calls, generating 50+ orders in seconds without a browser), `fast` (accelerated Chromium browser window), or `normal` (human-like visual shopping delays).
* **`razorpay_transactions_count`**: Total number of customer orders and payments to simulate (supported range: `10` to `2000`; default `60`).
* **`start_date` & `end_date`**: Defines the date window (`YYYY-MM-DD`) for all generated checkouts, webhook callbacks, and settlement entries.
* **`imputed_expenses_percentage`**: Percentage of non-gateway operational expenses added to the bank statement (e.g. 60 transactions at 20% injects 12 debits for office rent, electricity, vendor UPI, salaries) to verify that the 3-way matrix cleanly separates operating expenses from gateway payouts.
* **`bank_pdf_format`**: Chooses the statement template — `UNION_BANK` (7-column layout with account summary box) or `SBI` (8-column landscape layout).
* **`opening_balance`**: Starting bank balance on `start_date` used to compute running balances across the generated statement.
* **`mdr_rate_percent`**: Contracted Merchant Discount Rate SLA (e.g. `2.0%`) used by the engine to audit fee leakage.
* **`gst_rate_percent`**: Statutory GST applied on gateway MDR processing fees (e.g. `18.0%`).
* **`gstin` & `pan`**: Merchant tax identifiers used in settlement summaries and GSTR-3B Table 4A Input Tax Credit claims.
* **`is_tds_applicable` & `tds_rate_percent`**: Enables prototypic Section 194-O statutory tax withholding modeling. *Note: `tds_rate_percent = 1` is a configurable prototype demonstration rate for testing statutory deduction tracking.*

---

### Section B: Prototypic Commercial Edge Cases

```ini
[EDGE_CASES]
enable_edge_cases = true
dropped_webhook_count = 9
fee_overcharge_count = 5
orphan_refund_count = 10
chargeback_hold_count = 20

[RANGE_LIMITS]
min_transactions = 10
max_transactions = 2000
```

* **`enable_edge_cases`**: Master toggle — `true` injects controlled commercial anomalies into randomly selected transactions; `false` generates a 100% cleanly matched baseline.
* **`dropped_webhook_count`**: Number of orders where payment is captured and settled in the bank, but the store order status remains stuck in `PENDING` due to simulated network packet drop.
* **`fee_overcharge_count`**: Number of payments billed at an inflated interchange rate (~2.75% vs. 2.0% contracted SLA) to test fee leakage recovery.
* **`orphan_refund_count`**: Number of prior-period customer return refund deductions injected into the settlement payout with non-reversed gateway processing fees.
* **`chargeback_hold_count`**: Number of customer bank disputes that freeze order GMV into escrow and apply an administrative penalty (₹500 fee + ₹90 GST).
* **`min_transactions` & `max_transactions`**: Safety boundaries (`10` to `2000`) for simulator processing.

---

## 2. AI Model Selection & Resilient Fallbacks (`ai_models.ini`)

AutoReconAI uses Google Gemini for domain reasoning and synthesis. If any model encounters rate limits (HTTP 429) or downtime, the system automatically falls back through the sequential chain defined in `ai_models.ini`.

```ini
[GEMINI_MODELS]
current_model = gemini-3.5-flash-lite
fallback_model_1 = gemini-3.1-flash-lite
fallback_model_2 = gemini-flash-latest
fallback_model_3 = gemini-3.5-flash
fallback_model_4 = gemini-3.7-flash
fallback_model_5 = gemini-3.6-flash

[MODEL_SETTINGS]
temperature = 0.0
max_output_tokens = 2048
```

* **`current_model`**: Primary active model (`gemini-3.5-flash-lite`), high execution speed with 15 RPM / 500 RPD bucket and native function calling.
* **`fallback_model_1` to `5`**: Sequential fallback tier chain (`gemini-3.1-flash-lite` -> `gemini-flash-latest` -> `gemini-3.5-flash` -> `gemini-3.7-flash` -> `gemini-3.6-flash`) ensuring uninterrupted evaluation.
* **`temperature = 0.0`**: Strictly enforces deterministic factual grounding for financial data (zero creative hallucination).
* **`max_output_tokens = 2048`**: Response length cap for concise, structured markdown tables and formal dispute tickets.

---

## 🔄 How to Apply Configuration Changes

Whenever you modify any parameter in [`config.ini`](../config.ini) or [`ai_models.ini`](../ai_models.ini):

1. **Save the File:**  
   Press `Ctrl + S` in your code editor.
2. **Restart Running Services:**  
   In your running terminal windows, press `Ctrl + C` to stop `backend.py` and `run_razorpay_suite.py`, then re-run them:
   ```bash
   # Terminal 1:
   python backend.py 5050

   # Terminal 2:
   python run_razorpay_suite.py
   ```
3. **Re-Run Data Simulation:**  
   In Terminal 3, re-run the simulation pipeline so your new configuration parameters generate fresh datasets:
   ```bash
   # Terminal 3:
   python "Data Simulator & Generator/run_simulation_pipeline.py"
   ```
   > 💡 All three files in `generated_data/` will be cleanly regenerated and overwritten with your exact configuration values.
