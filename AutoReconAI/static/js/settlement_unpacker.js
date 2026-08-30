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

    document.getElementById('unpacker-sla-text').innerText = `Contracted SLA: ${sla.sla_text || '2.00% MDR + 18% GST'}`;
    document.getElementById('unpacker-gmv').innerText = `₹${formatInr(p.total_gmv)}`;
    document.getElementById('unpacker-payout').innerText = `₹${formatInr(p.net_bank_payout)}`;
    document.getElementById('unpacker-mdr').innerText = `₹${formatInr(p.total_mdr_expense)}`;
    document.getElementById('unpacker-gst').innerText = `₹${formatInr(p.total_gst_itc)}`;
    const refundLossEl = document.getElementById('unpacker-refund-loss');
    if (refundLossEl) refundLossEl.innerText = `₹${formatInr(p.total_non_recoverable_refund_loss)}`;

    document.getElementById('unpacker-payout-sub').innerText = `${p.proportions?.net_payout_percent || 0}% of gross sales credited to bank`;
    document.getElementById('unpacker-mdr-sub').innerText = `${p.proportions?.mdr_expense_percent || 0}% gateway processing fee deducted`;
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
      const totalTake = (data.unpacked_pillars.proportions.mdr_expense_percent + data.unpacked_pillars.proportions.gst_itc_percent).toFixed(2);
      takeRatePill.innerText = `Effective Gateway Take-Rate: ${totalTake}%`;
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
          if (val === undefined) return;
          const pct = ((val / gmv) * 100).toFixed(2);
          const textVal = `₹${val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
          const textPct = `(${pct}%)`;

          ctx.save();
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          
          // Draw Amount Label (Exact 2 Decimal Places)
          ctx.font = 'bold 11.5px Inter, sans-serif';
          ctx.fillStyle = '#0f172a';
          ctx.fillText(textVal, bar.x, bar.y - 16);

          // Draw Percentage Label
          ctx.font = '600 11px JetBrains Mono, monospace';
          ctx.fillStyle = index === 0 ? '#1d4ed8' : (index === 1 ? '#047857' : (index === 2 ? '#b45309' : (index === 3 ? '#6d28d9' : (index === 4 ? '#be123c' : '#dc2626'))));
          ctx.fillText(textPct, bar.x, bar.y - 2);

          ctx.restore();
        });
      }
    };

    chartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [
          'Gross Sales (GMV)',
          'Net Bank Deposited',
          'Gateway MDR Fee',
          'Claimable 18% GST (ITC)',
          'Customer Return Refunds',
          'Non-Recoverable Refund Loss'
        ],
        datasets: [{
          label: 'Amount (INR ₹)',
          data: [
            p.total_gmv || 0,
            p.net_bank_payout || 0,
            p.total_mdr_expense || 0,
            p.total_gst_itc || 0,
            p.total_customer_refunds || 0,
            p.total_non_recoverable_refund_loss || 0
          ],
          backgroundColor: [
            'rgba(59, 130, 246, 0.85)',   // Blue (GMV)
            'rgba(16, 185, 129, 0.85)',   // Green (Net Bank)
            'rgba(245, 158, 11, 0.85)',   // Amber (MDR)
            'rgba(139, 92, 246, 0.85)',   // Purple (GST ITC)
            'rgba(244, 63, 94, 0.85)',    // Rose (Refunds)
            'rgba(225, 29, 72, 0.85)'     // Crimson Red (Refund Loss)
          ],
          borderColor: [
            '#2563eb',
            '#059669',
            '#d97706',
            '#7c3aed',
            '#e11d48',
            '#be123c'
          ],
          borderWidth: 1.5,
          borderRadius: 8,
          barPercentage: 0.50
        }]
      },
      plugins: [topLabelsPlugin],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            top: 36
          }
        },
        animation: {
          duration: 900,
          easing: 'easeOutQuart'
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0c2340',
            titleFont: { size: 13, weight: '700' },
            bodyFont: { size: 13 },
            padding: 12,
            cornerRadius: 8,
            callbacks: {
              label: function(context) {
                const val = context.raw || 0;
                const gmv = p.total_gmv || 1;
                const pct = ((val / gmv) * 100).toFixed(2);
                return ` INR ₹${val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${pct}% of Total Gross Sales)`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              font: { weight: '600', size: 11 },
              color: '#334155'
            }
          },
          y: {
            beginAtZero: true,
            grid: { color: '#f1f5f9' },
            ticks: {
              callback: (val) => '₹' + (val >= 1000 ? (val / 1000).toFixed(0) + 'k' : val),
              color: '#64748b',
              font: { size: 11 }
            }
          }
        }
      }
    });
  }

  function renderFlowBar(data) {
    const props = data.unpacked_pillars?.proportions || {};
    const netPct = props.net_payout_percent || 93.64;
    const mdrPct = props.mdr_expense_percent || 2.51;
    const gstPct = props.gst_itc_percent || 0.45;
    const refundsPct = props.refunds_percent || 3.40;
    const lossPct = props.non_recoverable_loss_percent || 0.04;

    const flowNet = document.getElementById('flow-net');
    const flowMdr = document.getElementById('flow-mdr');
    const flowGst = document.getElementById('flow-gst');
    const flowRefunds = document.getElementById('flow-refunds');
    const flowLoss = document.getElementById('flow-loss');

    if (flowNet) flowNet.style.width = `${netPct}%`;
    if (flowMdr) flowMdr.style.width = `${mdrPct}%`;
    if (flowGst) flowGst.style.width = `${gstPct}%`;
    if (flowRefunds) flowRefunds.style.width = `${refundsPct}%`;
    if (flowLoss) flowLoss.style.width = `${lossPct}%`;

    const lblNet = document.getElementById('legend-net-label');
    const lblMdr = document.getElementById('legend-mdr-label');
    const lblGst = document.getElementById('legend-gst-label');
    const lblRefunds = document.getElementById('legend-refunds-label');
    const lblLoss = document.getElementById('legend-loss-label');

    if (lblNet) lblNet.innerText = `Net Bank Payout: ${netPct}%`;
    if (lblMdr) lblMdr.innerText = `Gateway MDR Fee: ${mdrPct}%`;
    if (lblGst) lblGst.innerText = `Claimable GST ITC: ${gstPct}%`;
    if (lblRefunds) lblRefunds.innerText = `Customer Refunds: ${refundsPct}%`;
    if (lblLoss) lblLoss.innerText = `Un-Reversed Refund Loss: ${lossPct}%`;

    const totalTakeRate = (mdrPct + gstPct).toFixed(2);
    const takeRateText = document.getElementById('flow-take-rate-text');
    if (takeRateText) takeRateText.innerText = `Effective Gateway Take-Rate: ${totalTakeRate}%`;
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
