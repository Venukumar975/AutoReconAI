# AutoReconAI - AI Agents Fixes & Improvements Plan

## 1. Issue Summary: Dispute Claim Amount Inconsistency

### Observed Behavior:
* **Turn 1 (Summary Query):**
  * User: *"ok now can u make a nice tabled summary of these mismatched orders and how much amount i can recover"*
  * `ReconAuditorAI` executed: `get_reconciliation_overview()`, `list_mismatches()`, `calculate_fee_discrepancies()`
  * Output: **₹85.57** claimable cash across 9 fee overcharge orders *(Mathematically exact)*.

* **Turn 2 (Dispute Ticket Generation):**
  * User: *"ok can u make a claim ticket for these recoverable money and a final summary"*
  * Intent Classified: `DISPUTE_CLAIM`
  * `ReconAuditorAI` executed: `get_reconciliation_overview()` **ONLY**
  * Output in Dispute Letter: **₹1,142.50** Total Claim Amount *(Hallucinated / Inconsistent)*.

---

## 2. Root Cause Analysis

1. **Tool Invocation Omission in `ReconAuditorAI`:**
   * When `SentinelRouterAI` tagged the intent as `DISPUTE_CLAIM`, `ReconAuditorAI` only called `get_reconciliation_overview()`.
   * `get_reconciliation_overview()` only provides counts and high-level GMV/fees; it does **not** calculate exact rupee overcharges per order.
   * `calculate_fee_discrepancies()` or `generate_dispute_ticket()` was omitted by the model in that turn.

2. **Absence of Tool Data in `PrecisionSynthesizerAI`:**
   * `PrecisionSynthesizerAI` received the auditor payload which had the list of 9 order IDs, but **lacked** `total_claimable_overcharge_inr`.
   * Tasked with generating an official claim letter with a total amount, the LLM synthesized an arbitrary figure (₹1,142.50) instead of falling back or requiring the calculation tool.

---

## 3. Action Items / Fixes Needed

### Fix 1: Strict Tool Association in `ReconAuditorAI` (`recon_auditor_agent.py`)
Add explicit deterministic instructions and prompt guidance:
* If Intent is `DISPUTE_CLAIM` or user mentions *"claim", "dispute", "recoverable money", "ticket"*:
  * **MUST ALWAYS EXECUTE** `calculate_fee_discrepancies()` or `generate_dispute_ticket()`.
  * Forbid responding with dispute letters unless `calculate_fee_discrepancies` payload is present.

### Fix 2: Anti-Hallucination Rule in `PrecisionSynthesizerAI` (`precision_synthesizer_agent.py`)
Add a hard constraint in the synthesis prompt:
* *"In dispute claim letters, the Total Claim Amount MUST strictly equal `tool_data.calculate_fee_discrepancies.total_claimable_overcharge_inr` or `tool_data.generate_dispute_ticket.total_claim_amount`. NEVER estimate, sum unverified fees, or hallucinate a claim amount if this key is missing."*

### Fix 3: Automatic Tool Fallback in `ReconAuditorAI`
In `recon_auditor_agent.py`, if the model's function calling loop finishes for intent `DISPUTE_CLAIM` without having called `calculate_fee_discrepancies`, automatically inject the output of `ReconToolbox.calculate_fee_discrepancies(session_data)` into `collected_tool_results` before handing over to `PrecisionSynthesizerAI`.

---

## 4. Current Status
* **Gateway Server & Dashboard:** Fully synchronized to `config.ini` (Dynamic MDR & GST rates).
* **Multi-Page Bank Parser:** Fixed (Extracts all pages without skipping rows).
* **AI Agent Flow:** 4-agent pipeline active; dispute claim tool association to be tightened as per above steps.
