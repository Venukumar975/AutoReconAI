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
  let chartInstance = null;

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
      renderExecutiveSummary(data);
      renderFinancialChart(data);
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

    const slaEl = document.getElementById('unpacker-sla-text');
    if (slaEl) slaEl.innerText = `Contracted SLA: ${sla.sla_text || '2.20% MDR + 18.30% GST'}`;

    const gmvEl = document.getElementById('unpacker-gmv');
    if (gmvEl) gmvEl.innerText = `₹${formatInr(p.total_gmv)}`;

    const payoutEl = document.getElementById('unpacker-payout');
    if (payoutEl) payoutEl.innerText = `₹${formatInr(p.net_bank_payout)}`;

    const mdrEl = document.getElementById('unpacker-mdr');
    if (mdrEl) mdrEl.innerText = `₹${formatInr(p.contracted_base_mdr || p.total_mdr_expense)}`;

    const gstEl = document.getElementById('unpacker-gst');
    if (gstEl) gstEl.innerText = `₹${formatInr(p.contracted_base_gst || p.total_gst_itc)}`;

    const refundLossEl = document.getElementById('unpacker-refund-loss');
    if (refundLossEl) refundLossEl.innerText = `₹${formatInr(p.refund_fee_leakage || p.total_non_recoverable_refund_loss)}`;

    const payoutSub = document.getElementById('unpacker-payout-sub');
    if (payoutSub) payoutSub.innerText = `${p.proportions?.net_payout_pct || 0}% of gross sales realized in bank`;

    const mdrSub = document.getElementById('unpacker-mdr-sub');
    if (mdrSub) mdrSub.innerText = `${p.proportions?.contracted_mdr_pct || 0}% contracted interchange fee`;

    // Populate Recovery Equation Card
    const claimableEl = document.getElementById('eq-claimable-overcharge');
    if (claimableEl) claimableEl.innerText = `₹${formatInr(p.total_claimable_overcharges)}`;

    const disputeEl = document.getElementById('eq-recoverable-dispute');
    if (disputeEl) disputeEl.innerText = `₹${formatInr(p.disputed_escrow_gmv)}`;

    const potentialEl = document.getElementById('eq-potential-bank');
    if (potentialEl) potentialEl.innerText = `₹${formatInr(p.potential_recovered_payout)}`;
  }

  function renderExecutiveSummary(data) {
    const summaryEl = document.getElementById('unpacker-executive-summary');
    const badgeEl = document.getElementById('unpacker-agent-badge');
    const takeRatePill = document.getElementById('chart-take-rate-pill');

    if (summaryEl) {
      summaryEl.innerText = data.executive_summary || 'Settlement batch successfully unpacked and verified.';
    }
    if (badgeEl && data.generated_by) {
      badgeEl.innerText = `🏷️ ${data.generated_by}`;
    }
    if (takeRatePill && data.unpacked_pillars?.proportions) {
      const slaPct = data.contracted_sla?.effective_sla_percent || 2.60;
      takeRatePill.innerText = `Contracted SLA Take-Rate: ${slaPct}%`;
    }
  }

  function renderFinancialChart(data) {
    const canvas = document.getElementById('unpacker-chart-canvas');
    if (!canvas || typeof Chart === 'undefined') return;

    const ctx = canvas.getContext('2d');
    const p = data.unpacked_pillars || {};

    if (chartInstance) {
      chartInstance.destroy();
    }

    const topLabelsPlugin = {
      id: 'topLabelsPlugin',
      afterDatasetsDraw(chart) {
        const { ctx, data } = chart;
        const gmv = p.total_gmv || 1;

        chart.getDatasetMeta(0).data.forEach((bar, index) => {
          const val = data.datasets[0].data[index];
          if (val === undefined || val === 0) return;
          const pct = ((val / gmv) * 100).toFixed(2);
          const textVal = `₹${val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
          const textPct = `(${pct}%)`;

          ctx.save();
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          
          // Draw Amount Label
          ctx.font = 'bold 11px Inter, sans-serif';
          ctx.fillStyle = '#0f172a';
          ctx.fillText(textVal, bar.x, bar.y - 15);

          // Draw Percentage Label
          ctx.font = '600 10.5px JetBrains Mono, monospace';
          ctx.fillStyle = '#475569';
          ctx.fillText(textPct, bar.x, bar.y - 2);

          ctx.restore();
        });
      }
    };

    const chartLabels = [
      'Gross Sales (GMV)',
      'Section 194-O TDS (1%)',
      'Contracted MDR',
      'Overcharged MDR',
      'Claimable 18% GST',
      'Overcharged GST',
      'Customer Refund GMV',
      'Refund Fee Loss',
      'Disputed GMV Hold',
      'Dispute Penalties',
      'Net Bank Deposited'
    ];

    const chartValues = [
      p.total_gmv || 0,
      p.total_tds_withheld || 0,
      p.contracted_base_mdr || 0,
      p.overcharged_mdr || 0,
      p.contracted_base_gst || 0,
      p.overcharged_gst || 0,
      p.customer_refund_gmv || 0,
      p.refund_fee_leakage || 0,
      p.disputed_escrow_gmv || 0,
      p.dispute_penalties || 0,
      p.net_bank_payout || 0
    ];

    const chartColors = [
      'rgba(59, 130, 246, 0.90)',   // 1. Blue (GMV)
      'rgba(99, 102, 241, 0.90)',   // 2. Indigo (TDS)
      'rgba(245, 158, 11, 0.90)',   // 3. Amber (Base MDR)
      'rgba(239, 68, 68, 0.90)',    // 4. Red (Overcharged MDR)
      'rgba(139, 92, 246, 0.90)',   // 5. Purple (Base GST ITC)
      'rgba(217, 70, 239, 0.90)',   // 6. Fuchsia (Overcharged GST)
      'rgba(244, 63, 94, 0.90)',    // 7. Rose (Refund GMV)
      'rgba(190, 18, 60, 0.90)',    // 8. Dark Crimson (Refund Fee Loss)
      'rgba(249, 115, 22, 0.90)',   // 9. Orange (Dispute Escrow)
      'rgba(185, 28, 28, 0.90)',    // 10. Deep Red (Dispute Penalties)
      'rgba(16, 185, 129, 0.95)'    // 11. Emerald Green (Net Bank)
    ];

    chartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: chartLabels,
        datasets: [{
          label: 'Amount (INR ₹)',
          data: chartValues,
          backgroundColor: chartColors,
          borderWidth: 1,
          borderColor: '#0f172a',
          borderRadius: 6,
          barPercentage: 0.65
        }]
      },
      plugins: [topLabelsPlugin],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            top: 36,
            bottom: 8
          }
        },
        animation: {
          duration: 800,
          easing: 'easeOutQuart'
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0c2340',
            titleFont: { size: 12, weight: '700' },
            bodyFont: { size: 12 },
            padding: 10,
            cornerRadius: 8,
            callbacks: {
              label: function(context) {
                const val = context.raw || 0;
                const gmv = p.total_gmv || 1;
                const pct = ((val / gmv) * 100).toFixed(2);
                return ` INR ₹${val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${pct}% of Gross Sales)`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              font: { weight: '600', size: 10 },
              color: '#334155',
              maxRotation: 25,
              minRotation: 20
            }
          },
          y: {
            beginAtZero: true,
            grid: { color: '#f1f5f9' },
            ticks: {
              callback: (val) => '₹' + (val >= 1000 ? (val / 1000).toFixed(0) + 'k' : val),
              color: '#64748b',
              font: { size: 10.5 }
            }
          }
        }
      }
    });
  }

  function renderFlowBar(data) {
    const props = data.unpacked_pillars?.proportions || {};
    const netPct = props.net_payout_pct || props.net_payout_percent || 93.64;
    const mdrPct = props.contracted_mdr_pct || props.mdr_expense_percent || 2.20;
    const overMdrPct = props.overcharged_mdr_pct || 0.0;
    const gstPct = props.contracted_gst_pct || props.gst_itc_percent || 0.40;
    const refundsPct = props.refunds_pct || props.refunds_percent || 0.0;
    const lossPct = props.refund_leakage_pct || props.non_recoverable_loss_percent || 0.0;
    const dispPct = props.dispute_escrow_pct || 0.0;

    const flowNet = document.getElementById('flow-net');
    const flowMdr = document.getElementById('flow-mdr');
    const flowGst = document.getElementById('flow-gst');
    const flowRefunds = document.getElementById('flow-refunds');
    const flowLoss = document.getElementById('flow-loss');

    if (flowNet) flowNet.style.width = `${netPct}%`;
    if (flowMdr) flowMdr.style.width = `${(mdrPct + overMdrPct).toFixed(2)}%`;
    if (flowGst) flowGst.style.width = `${gstPct}%`;
    if (flowRefunds) flowRefunds.style.width = `${(refundsPct + dispPct).toFixed(2)}%`;
    if (flowLoss) flowLoss.style.width = `${lossPct}%`;

    const lblNet = document.getElementById('legend-net-label');
    const lblMdr = document.getElementById('legend-mdr-label');
    const lblGst = document.getElementById('legend-gst-label');
    const lblRefunds = document.getElementById('legend-refunds-label');
    const lblLoss = document.getElementById('legend-loss-label');

    if (lblNet) lblNet.innerText = `Net Bank Payout: ${netPct}%`;
    if (lblMdr) lblMdr.innerText = `Gateway MDR: ${(mdrPct + overMdrPct).toFixed(2)}%`;
    if (lblGst) lblGst.innerText = `Claimable GST ITC: ${gstPct}%`;
    if (lblRefunds) lblRefunds.innerText = `Refunds & Disputes: ${(refundsPct + dispPct).toFixed(2)}%`;
    if (lblLoss) lblLoss.innerText = `Un-Reversed Fee Loss: ${lossPct}%`;

    const totalTakeRate = (mdrPct + overMdrPct + gstPct).toFixed(2);
    const takeRateText = document.getElementById('flow-take-rate-text');
    if (takeRateText) takeRateText.innerText = `Effective Gateway Take-Rate: ${totalTakeRate}%`;
  }

  function renderBuckets(data) {
    const buckets = data.categorized_buckets || {};
    const formatInr = (val) => (val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    // 1. Overcharges
    const overcharges = buckets.mdr_overcharges || buckets.fee_overcharges || {};
    const overchargeCountEl = document.getElementById('bucket-overcharge-count');
    if (overchargeCountEl) overchargeCountEl.innerText = `${overcharges.count || 0} Orders`;
    const overchargeClaimEl = document.getElementById('bucket-overcharge-claim');
    if (overchargeClaimEl) overchargeClaimEl.innerText = `Claimable Cash: ₹${formatInr(overcharges.total_claimable_inr)}`;
    
    const overchargeTags = document.getElementById('bucket-overcharge-tags');
    if (overchargeTags) {
      overchargeTags.innerHTML = '';
      (overcharges.orders || []).forEach(o => {
        const span = document.createElement('span');
        span.className = 'order-pill overcharge';
        span.innerText = `${o.order_id} (Claim: ₹${o.claimable_overcharge})`;
        span.title = `Billed at ${o.billed_rate} vs contracted ${o.contracted_rate}`;
        overchargeTags.appendChild(span);
      });
    }

    // 2. Dropped Webhooks
    const webhooks = buckets.dropped_webhooks || {};
    const webhookCountEl = document.getElementById('bucket-webhook-count');
    if (webhookCountEl) webhookCountEl.innerText = `${webhooks.count || 0} Orders`;
    
    const webhookTags = document.getElementById('bucket-webhook-tags');
    if (webhookTags) {
      webhookTags.innerHTML = '';
      (webhooks.orders || []).forEach(w => {
        const span = document.createElement('span');
        span.className = 'order-pill webhook';
        span.innerText = `${w.order_id} (₹${formatInr(w.amount)})`;
        span.title = `Payment captured at gateway; Store status PENDING`;
        webhookTags.appendChild(span);
      });
    }

    // 3. Customer Refunds / Orphan Returns
    const refunds = buckets.customer_refunds || buckets.orphan_refunds || {};
    const refundCountEl = document.getElementById('bucket-refund-count');
    if (refundCountEl) refundCountEl.innerText = `${refunds.count || 0} Orders`;
    const refundDeductEl = document.getElementById('bucket-refund-deduction');
    if (refundDeductEl) refundDeductEl.innerText = `Total Debited: ₹${formatInr(refunds.total_amount_inr || refunds.total_deduction_inr)}`;

    const refundTags = document.getElementById('bucket-refund-tags');
    if (refundTags) {
      refundTags.innerHTML = '';
      (refunds.orders || []).forEach(r => {
        const span = document.createElement('span');
        span.className = 'order-pill refund';
        span.innerText = `${r.order_id} (-₹${formatInr(r.deduction_amount)})`;
        span.title = r.reason || 'Customer refund';
        refundTags.appendChild(span);
      });
    }
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
          <span>${faq.question}</span>
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
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }
  }

  return {
    loadAndRenderReport,
    reset
  };

})();
