/**
 * AutoReconAI - File Uploader & Sequential Step Coordinator
 * Manages dropzones, file API requests, and triggers preview updates.
 */

const Uploader = (() => {

  function init() {
    setupOrdersDropzone();
    setupBankDropzone();
    setupSettlementDropzone();
  }

  // 1. Orders Dropzone Setup
  function setupOrdersDropzone() {
    const card = document.getElementById('card-step-orders');
    const dropzone = document.getElementById('dropzone-orders');
    const input = document.getElementById('input-file-orders');

    setupDragEvents(dropzone, input);

    input.addEventListener('change', async (e) => {
      if (e.target.files.length > 0) {
        await uploadOrdersFile(e.target.files[0]);
      }
    });
  }

  async function uploadOrdersFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const card = document.getElementById('card-step-orders');
    const dropzone = document.getElementById('dropzone-orders');
    const uploadedState = document.getElementById('uploaded-orders');

    dropzone.style.display = 'none';

    try {
      const resp = await fetch('/api/upload/orders', {
        method: 'POST',
        body: formData
      });

      const data = await resp.json();
      if (!data.success) {
        alert(`Error uploading orders: ${data.error}`);
        dropzone.style.display = 'flex';
        return;
      }

      // Populate file meta
      document.getElementById('name-orders').innerText = data.filename;
      document.getElementById('stat-orders-count').innerText = `${data.total_orders} Orders`;
      document.getElementById('stat-orders-gmv').innerText = `₹${data.total_gmv.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

      uploadedState.style.display = 'flex';
      card.classList.remove('active-step');
      card.classList.add('completed');

      // Move active state to Step 2
      document.getElementById('card-step-bank').classList.add('active-step');
      
      const n1 = document.getElementById('step-node-1');
      const n2 = document.getElementById('step-node-2');
      if (n1) {
        n1.classList.remove('active');
        n1.classList.add('completed');
        const b1 = document.getElementById('badge-node-1');
        if (b1) b1.innerText = '✓';
        const s1 = document.getElementById('status-node-1');
        if (s1) s1.innerHTML = 'Step 1 &bull; Completed';
      }
      if (n2) {
        n2.classList.add('active');
        const s2 = document.getElementById('status-node-2');
        if (s2) s2.innerHTML = 'Step 2 &bull; Active';
      }
      const fill1 = document.getElementById('timeline-progress-fill');
      if (fill1) fill1.style.width = '50%';

      App.checkPipelineReady();
      if (typeof AIAssistant !== 'undefined') AIAssistant.updateIngestionProgress(1);

    } catch (e) {
      alert(`Network error uploading orders: ${e.message}`);
      dropzone.style.display = 'flex';
    }
  }

  // 2. Bank Statement Dropzone Setup (PDF / Excel with Table Detection)
  function setupBankDropzone() {
    const card = document.getElementById('card-step-bank');
    const dropzone = document.getElementById('dropzone-bank');
    const input = document.getElementById('input-file-bank');

    setupDragEvents(dropzone, input);

    input.addEventListener('change', async (e) => {
      if (e.target.files.length > 0) {
        await detectBankFile(e.target.files[0]);
      }
    });
  }

  async function detectBankFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const dropzone = document.getElementById('dropzone-bank');
    const originalText = dropzone.querySelector('.dropzone-text').innerText;
    dropzone.querySelector('.dropzone-text').innerText = '⏳ Scanning table structure (>= 5 columns)...';

    try {
      const resp = await fetch('/api/upload/detect-bank-table', {
        method: 'POST',
        body: formData
      });

      const data = await resp.json();
      dropzone.querySelector('.dropzone-text').innerText = originalText;

      if (!data.success) {
        alert(`Table Detection Failed: ${data.error}`);
        return;
      }

      // Open interactive Header Mapping Modal
      MapperModal.open(data, (processedResult) => {
        onBankMappingCompleted(data.filename, processedResult);
      });

    } catch (e) {
      dropzone.querySelector('.dropzone-text').innerText = originalText;
      alert(`Network error detecting bank table: ${e.message}`);
    }
  }

  function onBankMappingCompleted(filename, result) {
    const card = document.getElementById('card-step-bank');
    const dropzone = document.getElementById('dropzone-bank');
    const uploadedState = document.getElementById('uploaded-bank');

    dropzone.style.display = 'none';

    document.getElementById('name-bank').innerText = filename;
    
    // 1. Opening Balance
    const opBal = result.opening_balance !== undefined ? result.opening_balance : 25000.00;
    const opType = result.opening_balance_type || (opBal >= 0 ? 'Cr' : 'Dr');
    const opEl = document.getElementById('stat-bank-opening');
    if (opEl) {
      opEl.innerText = `₹${Math.abs(opBal).toLocaleString('en-IN', { minimumFractionDigits: 2 })} ${opType}`;
      opEl.style.color = opBal >= 0 ? '#059669' : '#dc2626';
    }

    // 2. Vouchers / Entries Count
    const countEl = document.getElementById('stat-bank-count');
    if (countEl) {
      countEl.innerText = `${result.total_transactions || 0} Vouchers`;
    }

    // 3. Bank Closing Balance
    const closeBal = result.closing_balance !== undefined ? result.closing_balance : (opBal + (result.total_credits || 0) - (result.total_debits || 0));
    const closeType = result.closing_balance_type || (closeBal >= 0 ? 'Cr' : 'Dr');
    const closeEl = document.getElementById('stat-bank-closing');
    if (closeEl) {
      closeEl.innerText = `₹${Math.abs(closeBal).toLocaleString('en-IN', { minimumFractionDigits: 2 })} ${closeType}`;
      closeEl.style.color = closeBal >= 0 ? '#059669' : '#dc2626';
    }

    // If settlements already in session, apply gateway reconciled stats immediately
    if (result.bank_card_update) {
      const bUp = result.bank_card_update;
      if (countEl) countEl.innerText = `${bUp.vouchers_count || 0} Vouchers`;
      if (closeEl) {
        closeEl.innerText = `₹${Math.abs(bUp.closing_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })} ${bUp.closing_balance_type || 'Cr'}`;
        closeEl.style.color = bUp.is_closing_positive ? '#059669' : '#dc2626';
      }
      const bankTag = card.querySelector('.file-stats-tag');
      if (bankTag) {
        bankTag.innerText = 'Gateway Reconciled';
        bankTag.style.backgroundColor = '#ecfdf5';
        bankTag.style.color = '#059669';
      }
    }

    uploadedState.style.display = 'flex';
    card.classList.remove('active-step');
    card.classList.add('completed');

    // Move active state to Step 3
    document.getElementById('card-step-settlement').classList.add('active-step');
    
    const n2 = document.getElementById('step-node-2');
    const n3 = document.getElementById('step-node-3');
    if (n2) {
      n2.classList.remove('active');
      n2.classList.add('completed');
      const b2 = document.getElementById('badge-node-2');
      if (b2) b2.innerText = '✓';
      const s2 = document.getElementById('status-node-2');
      if (s2) s2.innerHTML = 'Step 2 &bull; Completed';
    }
    if (n3) {
      n3.classList.add('active');
      const s3 = document.getElementById('status-node-3');
      if (s3) s3.innerHTML = 'Step 3 &bull; Active';
    }
    const fill2 = document.getElementById('timeline-progress-fill');
    if (fill2) fill2.style.width = '80%';

    App.checkPipelineReady();
  }

  // 3. Settlement Dropzone Setup
  function setupSettlementDropzone() {
    const card = document.getElementById('card-step-settlement');
    const dropzone = document.getElementById('dropzone-settlement');
    const input = document.getElementById('input-file-settlement');

    setupDragEvents(dropzone, input);

    input.addEventListener('change', async (e) => {
      if (e.target.files.length > 0) {
        await uploadSettlementFile(e.target.files[0]);
      }
    });
  }

  async function uploadSettlementFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const card = document.getElementById('card-step-settlement');
    const dropzone = document.getElementById('dropzone-settlement');
    const uploadedState = document.getElementById('uploaded-settlement');

    dropzone.style.display = 'none';

    try {
      const resp = await fetch('/api/upload/settlement', {
        method: 'POST',
        body: formData
      });

      const data = await resp.json();
      if (!data.success) {
        alert(`Error uploading settlement CSV: ${data.error}`);
        dropzone.style.display = 'flex';
        return;
      }

      document.getElementById('name-settlement').innerText = data.filename;
      document.getElementById('stat-settlement-count').innerText = `${data.total_records} Payouts`;
      document.getElementById('stat-settlement-net').innerText = `₹${data.total_net_credit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

      // Live dynamic refresh of Bank Statement card to match Gateway Settlement ledger
      const proceedBtn = document.getElementById('btn-proceed-recon');
      const proceedSubtext = document.getElementById('proceed-subtext');
      if (proceedBtn) {
        proceedBtn.disabled = true;
        proceedBtn.innerHTML = `<span>⚡ Reconciling Gateway UTRs with Bank Statement...</span>`;
      }

      uploadedState.style.display = 'flex';
      card.classList.remove('active-step');
      card.classList.add('completed');
      
      const n3 = document.getElementById('step-node-3');
      if (n3) {
        n3.classList.remove('active');
        n3.classList.add('completed');
        const b3 = document.getElementById('badge-node-3');
        if (b3) b3.innerText = '✓';
        const s3 = document.getElementById('status-node-3');
        if (s3) s3.innerHTML = 'Step 3 &bull; Completed';
      }
      const fill3 = document.getElementById('timeline-progress-fill');
      if (fill3) fill3.style.width = '100%';

      if (data.bank_card_update) {
        const bCard = document.getElementById('card-step-bank');
        const bankTag = bCard ? bCard.querySelector('.file-stats-tag') : null;
        if (bankTag) {
          bankTag.innerText = '⚡ Matching UTRs...';
          bankTag.style.backgroundColor = '#fef3c7';
          bankTag.style.color = '#d97706';
        }

        setTimeout(() => {
          const bUp = data.bank_card_update;
          const countEl = document.getElementById('stat-bank-count');
          if (countEl) {
            countEl.innerText = `${bUp.vouchers_count || 0} Vouchers`;
          }
          const closeEl = document.getElementById('stat-bank-closing');
          if (closeEl) {
            closeEl.innerText = `₹${Math.abs(bUp.closing_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })} ${bUp.closing_balance_type || 'Cr'}`;
            closeEl.style.color = bUp.is_closing_positive ? '#059669' : '#dc2626';
          }
          if (bankTag) {
            bankTag.innerText = 'Gateway Reconciled';
            bankTag.style.backgroundColor = '#ecfdf5';
            bankTag.style.color = '#059669';
          }

          // Unlock Pipeline Ready
          if (proceedBtn) {
            proceedBtn.disabled = false;
            proceedBtn.innerHTML = `<span>Proceed to 3-Way Reconciliation Matrix</span><span>➔</span>`;
          }
          App.checkPipelineReady();
          if (typeof AIAssistant !== 'undefined') AIAssistant.updateIngestionProgress(3);
        }, 700);
      } else {
        if (proceedBtn) {
          proceedBtn.disabled = false;
          proceedBtn.innerHTML = `<span>Proceed to 3-Way Reconciliation Matrix</span><span>➔</span>`;
        }
        App.checkPipelineReady();
        if (typeof AIAssistant !== 'undefined') AIAssistant.updateIngestionProgress(3);
      }

    } catch (e) {
      alert(`Network error uploading settlement CSV: ${e.message}`);
      dropzone.style.display = 'flex';
    }
  }

  // Helper for drag & drop visual styling
  function setupDragEvents(dropzone, input) {
    dropzone.addEventListener('click', () => input.click());

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
      dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        input.files = e.dataTransfer.files;
        input.dispatchEvent(new Event('change'));
      }
    });
  }

  return {
    init
  };
})();
