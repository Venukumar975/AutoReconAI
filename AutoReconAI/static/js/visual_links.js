/**
 * AutoReconAI - Grouped Reconciliation Table Renderer
 * Matches the user's handwritten table diagram EXACTLY:
 * [ UTR No ] | [ Ord ID's ] | [ Date ] | [ Billed ] | [ MDR (2%) ] | [ GST (18%) ] | [ Net Payout ] | [ Matched ] | [ Settled ]
 */

const VisualLinks = (() => {

  function renderGroupedUTRMatrix(data) {
    const tbody = document.getElementById('grouped-recon-tbody');
    const totalGroupsBadge = document.getElementById('matrix-group-count');

    // Populate Top KPI Cards
    if (data.summary) {
      document.getElementById('kpi-gmv').innerText = `₹${data.summary.total_gmv.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
      document.getElementById('kpi-bank-deposit').innerText = `₹${data.summary.total_bank_deposited.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
      document.getElementById('kpi-fees').innerText = `₹${data.summary.total_fees.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
      document.getElementById('kpi-gst').innerText = `₹${data.summary.total_gst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
      document.getElementById('kpi-match-rate').innerText = data.summary.match_rate;

      const expectedMdr = (data.summary.total_gmv || 0) * ((data.summary.contracted_mdr_percent || 2.1) / 100);
      const hasOvercharge = (data.summary.total_fees || 0) > (expectedMdr + 0.5);

      const feesEl = document.getElementById('kpi-fees');
      const gstEl = document.getElementById('kpi-gst');
      const mdrCard = feesEl ? feesEl.closest('.kpi-card') : null;
      const gstCard = gstEl ? gstEl.closest('.kpi-card') : null;

      if (data.summary.contracted_mdr_percent) {
        const mdrLabel = document.getElementById('kpi-mdr-label');
        if (mdrLabel) {
          mdrLabel.innerHTML = hasOvercharge
            ? `MDR Fees (${data.summary.contracted_mdr_percent}%) <span style="color:#b45309; font-size:10px; font-weight:700; background:#fef3c7; padding:2px 6px; border-radius:4px; margin-left:4px;">⚠️ Overcharged</span>`
            : `MDR Fees (${data.summary.contracted_mdr_percent}%)`;
        }
        const thMdr = document.getElementById('th-mdr-label');
        if (thMdr) thMdr.innerText = `MDR (${data.summary.contracted_mdr_percent}%)`;
      }
      if (data.summary.gst_rate_percent) {
        const gstLabel = document.getElementById('kpi-gst-label');
        if (gstLabel) {
          gstLabel.innerHTML = hasOvercharge
            ? `GST on MDR (${data.summary.gst_rate_percent}%) <span style="color:#b45309; font-size:10px; font-weight:700; background:#fef3c7; padding:2px 6px; border-radius:4px; margin-left:4px;">⚠️ Overcharged</span>`
            : `GST on MDR (${data.summary.gst_rate_percent}%)`;
        }
        const thGst = document.getElementById('th-gst-label');
        if (thGst) thGst.innerText = `GST (${data.summary.gst_rate_percent}%)`;
      }

      if (hasOvercharge) {
        if (mdrCard) mdrCard.style.borderColor = "#f59e0b";
        if (gstCard) gstCard.style.borderColor = "#f59e0b";
      } else {
        if (mdrCard) mdrCard.style.borderColor = "";
        if (gstCard) gstCard.style.borderColor = "";
      }
    }

    totalGroupsBadge.innerText = `${data.utr_groups.length} Settlement Batches`;
    tbody.innerHTML = '';

    if (typeof AIAssistant !== 'undefined' && data.summary) {
      AIAssistant.updateReconStatus(data.summary.mismatched_count || 0);
    }

    // Render Table Rows grouped by Settlement UTR
    data.utr_groups.forEach(group => {
      const orders = group.orders || [];
      const orderCount = orders.length;

      orders.forEach((order, idx) => {
        const tr = document.createElement('tr');
        if (idx === orderCount - 1) {
          tr.className = 'group-boundary-row';
        }

        let rowHtml = '';

        // 1. Column 1: 'UTR No' (Spans all child order rows for this UTR, with Bank deposit & Bank Date)
        if (idx === 0) {
          rowHtml += `
            <td rowspan="${orderCount}" class="utr-floating-cell">
              <div class="utr-container-vertical">
                <span class="utr-code-badge">${group.settlement_utr}</span>
                ${group.bank_date ? `<span class="utr-date-sub">🗓️ ${group.bank_date}</span>` : ''}
                <span class="utr-deposit-amount">Bank: ₹${group.bank_deposited.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
            </td>
          `;
        }

        // 2. Child Order columns matching handwritten diagram
        rowHtml += `
          <!-- 2. Ord ID's -->
          <td style="font-weight: 700; color: var(--primary-navy);">
            <span class="order-tag">${order.order_id}</span>
          </td>

          <!-- 3. Date -->
          <td style="text-align: center; color: var(--text-secondary); font-size: 11.5px;">
            ${order.date}
          </td>

          <!-- 4. Billed -->
          <td style="text-align: right; font-weight: 600;">
            ₹${order.billed.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </td>

          <!-- 5. MDR (2%) -->
          <td style="text-align: right; color: var(--accent-orange); font-weight: 600;">
            ₹${order.mdr.toFixed(2)}
          </td>

          <!-- 6. GST (18%) -->
          <td style="text-align: right; color: var(--text-secondary);">
            ₹${order.gst.toFixed(2)}
          </td>

          <!-- 7. Net Payout -->
          <td style="text-align: right; font-weight: 700; color: var(--accent-green);">
            ₹${order.net_payout.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </td>

          <!-- 8. Matched -->
          <td style="text-align: center;">
            <span class="badge-status ${order.is_mismatched ? 'badge-mismatched' : 'badge-matched'}">
              ${order.is_mismatched ? '⚠️ Mismatched' : '✅ Matched'}
            </span>
          </td>

          <!-- 9. Settled -->
          <td style="text-align: center;">
            <div class="utr-progress-box">
              <div class="progress-track">
                <div class="progress-fill" style="width: ${order.is_mismatched ? '25%' : '100%'}; background: ${order.is_mismatched ? 'linear-gradient(90deg, #ef4444, #f97316)' : '#10b981'};"></div>
              </div>
              <span class="progress-text" style="color: ${order.is_mismatched ? '#dc2626' : '#059669'}; font-weight: 700;">
                ${order.is_mismatched ? 'Discrepancy' : 'matched 100%'}
              </span>
            </div>
          </td>
        `;

        tr.innerHTML = rowHtml;
        tbody.appendChild(tr);
      });
    });
  }

  return {
    renderGroupedUTRMatrix
  };
})();
