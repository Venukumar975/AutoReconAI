/**
 * AutoReconAI - Settlement Unpacker Client Controller
 * ====================================================
 * Renders the Settlement Unpacker & Tax/Sales Executive Hub:
 * 1. Shows sleek AI loading state during computation
 * 2. Populates 4 Core Pillars (GMV, Payout, MDR Expense, 18% GST ITC)
 * 3. Animates the proportional $100 flow bar
 * 4. Displays Edge Case Order Classification buckets
 * 5. Expands AI Controller Smart FAQs & Tax Deductible Insights
 */

const SettlementUnpacker = (() => {

  let isLoaded = false;

  async function loadAndRenderReport() {
    const skeleton = document.getElementById('unpacker-skeleton');
    const content = document.getElementById('unpacker-content');

    if (!skeleton || !content) return;

    // 1. Show skeleton loader
    skeleton.style.display = 'flex';
    content.style.display = 'none';

    try {
      const resp = await fetch('/api/unpacker/generate-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await resp.json();

      if (!data.success) {
        skeleton.innerHTML = `
          <div style="color: #ef4444; font-weight: 700; font-size: 16px;">⚠️ ${data.error || 'Failed to generate report.'}</div>
          <div style="color: #64748b; font-size: 13px; margin-top: 6px;">Please make sure Store Orders CSV and Settlement CSV are uploaded in Data Ingestion Hub.</div>
        `;
        return;
      }

      renderPillars(data);
      renderFlowBar(data);
      renderBuckets(data);
      renderFAQs(data);

      // Hide skeleton & show content
      skeleton.style.display = 'none';
      content.style.display = 'flex';
      isLoaded = true;

    } catch (err) {
      skeleton.innerHTML = `
        <div style="color: #ef4444; font-weight: 700; font-size: 16px;">⚠️ Error loading settlement unpacker</div>
        <div style="color: #64748b; font-size: 13px; margin-top: 6px;">${err.message}</div>
      `;
    }
  }

  function renderPillars(data) {
    const p = data.unpacked_pillars || {};
    const sla = data.contracted_sla || {};

    const formatInr = (val) => (val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    document.getElementById('unpacker-sla-text').innerText = `Contracted SLA: ${sla.sla_text || '2.00% MDR + 18% GST'}`;
    document.getElementById('unpacker-gmv').innerText = `₹${formatInr(p.total_gmv)}`;
    document.getElementById('unpacker-payout').innerText = `₹${formatInr(p.net_bank_payout)}`;
    document.getElementById('unpacker-mdr').innerText = `₹${formatInr(p.total_mdr_expense)}`;
    document.getElementById('unpacker-gst').innerText = `₹${formatInr(p.total_gst_itc)}`;

    document.getElementById('unpacker-payout-sub').innerText = `${p.proportions?.net_payout_percent || 0}% of gross sales credited to bank`;
    document.getElementById('unpacker-mdr-sub').innerText = `${p.proportions?.mdr_expense_percent || 0}% gateway processing fee deducted`;
  }

  function renderFlowBar(data) {
    const props = data.unpacked_pillars?.proportions || {};
    const netPct = props.net_payout_percent || 97.64;
    const mdrPct = props.mdr_expense_percent || 2.00;
    const gstPct = props.gst_itc_percent || 0.36;

    document.getElementById('flow-net').style.width = `${netPct}%`;
    document.getElementById('flow-mdr').style.width = `${mdrPct}%`;
    document.getElementById('flow-gst').style.width = `${gstPct}%`;

    document.getElementById('legend-net-label').innerText = `Net Bank Payout: ${netPct}%`;
    document.getElementById('legend-mdr-label').innerText = `Gateway MDR Fee: ${mdrPct}%`;
    document.getElementById('legend-gst-label').innerText = `Claimable GST ITC: ${gstPct}%`;

    const totalTakeRate = (mdrPct + gstPct).toFixed(2);
    document.getElementById('flow-take-rate-text').innerText = `Effective Gateway Take-Rate: ${totalTakeRate}%`;
  }

  function renderBuckets(data) {
    const buckets = data.categorized_buckets || {};
    const formatInr = (val) => (val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    // 1. Overcharges
    const overcharges = buckets.fee_overcharges || {};
    document.getElementById('bucket-overcharge-count').innerText = `${overcharges.count || 0} Orders`;
    document.getElementById('bucket-overcharge-claim').innerText = `Claimable Cash: ₹${formatInr(overcharges.total_claimable_inr)}`;
    
    const overchargeTags = document.getElementById('bucket-overcharge-tags');
    overchargeTags.innerHTML = '';
    (overcharges.orders || []).forEach(o => {
      const span = document.createElement('span');
      span.className = 'order-pill overcharge';
      span.innerText = `${o.order_id} (Claim: ₹${o.claimable_overcharge})`;
      span.title = `Billed at ${o.billed_rate} vs contracted ${o.contracted_rate}`;
      overchargeTags.appendChild(span);
    });

    // 2. Dropped Webhooks
    const webhooks = buckets.dropped_webhooks || {};
    document.getElementById('bucket-webhook-count').innerText = `${webhooks.count || 0} Orders`;
    const webhookTags = document.getElementById('bucket-webhook-tags');
    webhookTags.innerHTML = '';
    (webhooks.orders || []).forEach(o => {
      const span = document.createElement('span');
      span.className = 'order-pill webhook';
      span.innerText = `${o.order_id} (₹${formatInr(o.amount)})`;
      span.title = `Store status is PENDING, but gateway captured payment`;
      webhookTags.appendChild(span);
    });

    // 3. Orphan Refunds
    const orphans = buckets.orphan_refunds || {};
    document.getElementById('bucket-orphan-count').innerText = `${orphans.count || 0} Orders`;
    document.getElementById('bucket-orphan-deduction').innerText = `Total Deductions: ₹${formatInr(orphans.total_deduction_inr)}`;
    const orphanTags = document.getElementById('bucket-orphan-tags');
    orphanTags.innerHTML = '';
    (orphans.orders || []).forEach(o => {
      const span = document.createElement('span');
      span.className = 'order-pill orphan';
      span.innerText = `${o.order_id} (-₹${formatInr(o.deduction_amount)})`;
      span.title = o.reason;
      orphanTags.appendChild(span);
    });
  }

  function renderFAQs(data) {
    const faqsList = document.getElementById('unpacker-faqs-list');
    faqsList.innerHTML = '';

    const faqs = data.financial_faqs || [];
    faqs.forEach((faq, idx) => {
      const item = document.createElement('div');
      item.className = 'faq-item';
      item.innerHTML = `
        <div class="faq-question" onclick="this.parentElement.querySelector('.faq-answer').style.display = this.parentElement.querySelector('.faq-answer').style.display === 'none' ? 'block' : 'none'">
          <span>${idx + 1}. ${faq.question}</span>
          <span style="font-size: 12px; color: #64748b;">▼</span>
        </div>
        <div class="faq-answer">
          ${faq.answer}
        </div>
      `;
      faqsList.appendChild(item);
    });
  }

  function reset() {
    isLoaded = false;
  }

  return {
    loadAndRenderReport,
    reset
  };

})();
