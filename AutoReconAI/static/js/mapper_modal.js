/**
 * AutoReconAI - Bank Statement Header Mapping Modal Manager
 * Allows mapping any detected column or choosing '-- Ignore / Skip Column --'
 */

const MapperModal = (() => {
  let detectedHeaders = [];
  let onMappingAppliedCallback = null;

  function open(data, onAppliedCallback) {
    detectedHeaders = data.detected_headers || [];
    onMappingAppliedCallback = onAppliedCallback;

    const modal = document.getElementById('mapping-modal');
    const modalSubtitle = document.getElementById('modal-bank-filename');
    modalSubtitle.innerText = `Detected ${detectedHeaders.length} columns from ${data.filename} (${data.total_extracted_rows} rows found)`;

    // Populate all dropdowns with detected header options and explicit Ignore/Skip choice
    populateDropdown('map-txn-date', detectedHeaders, data.suggested_mapping.txn_date);
    populateDropdown('map-primary-narr', detectedHeaders, data.suggested_mapping.primary_narration);
    populateDropdown('map-secondary-narr', detectedHeaders, data.suggested_mapping.secondary_narration);
    populateDropdown('map-debit', detectedHeaders, data.suggested_mapping.debit);
    populateDropdown('map-credit', detectedHeaders, data.suggested_mapping.credit);
    populateDropdown('map-balance', detectedHeaders, data.suggested_mapping.balance);

    // Set auto-detected opening balance or default 10,000.00 fallback
    const opBalInput = document.getElementById('map-opening-balance');
    if (opBalInput) {
      opBalInput.value = data.detected_opening_balance !== undefined ? data.detected_opening_balance : 10000.00;
    }

    // Populate sample table preview
    renderRawPreview(detectedHeaders, data.preview_rows || []);

    modal.style.display = 'flex';
  }

  function populateDropdown(elementId, headers, selectedValue) {
    const select = document.getElementById(elementId);
    select.innerHTML = '';

    // Explicit Ignore / Skip Option (available on ALL keys)
    const ignoreOpt = document.createElement('option');
    ignoreOpt.value = '';
    ignoreOpt.innerText = '-- Ignore / Skip Column --';
    select.appendChild(ignoreOpt);

    headers.forEach(h => {
      const opt = document.createElement('option');
      opt.value = h;
      opt.innerText = h;
      if (selectedValue && h === selectedValue) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
  }

  function renderRawPreview(headers, rows) {
    const thead = document.getElementById('modal-raw-thead');
    const tbody = document.getElementById('modal-raw-tbody');

    thead.innerHTML = '';
    tbody.innerHTML = '';

    const trHead = document.createElement('tr');
    headers.forEach(h => {
      const th = document.createElement('th');
      th.innerText = h;
      trHead.appendChild(th);
    });
    thead.appendChild(trHead);

    rows.forEach(row => {
      const tr = document.createElement('tr');
      headers.forEach((_, idx) => {
        const td = document.createElement('td');
        td.innerText = row[idx] || '-';
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  function close() {
    document.getElementById('mapping-modal').style.display = 'none';
  }

  async function submitMapping() {
    const txnDate = document.getElementById('map-txn-date').value;
    const debit = document.getElementById('map-debit').value;
    const credit = document.getElementById('map-credit').value;
    const balance = document.getElementById('map-balance').value;
    const primaryNarr = document.getElementById('map-primary-narr').value;
    const secondaryNarr = document.getElementById('map-secondary-narr').value;
    const opBalVal = parseFloat(document.getElementById('map-opening-balance').value) || 10000.00;

    const mapping = {
      txn_date: txnDate || null,
      debit: debit || null,
      credit: credit || null,
      balance: balance || null,
      primary_narration: primaryNarr || null,
      secondary_narration: secondaryNarr || null
    };

    const submitBtn = document.getElementById('btn-apply-mapping');
    submitBtn.disabled = true;
    submitBtn.innerText = '⏳ Processing Statement...';

    try {
      const resp = await fetch('/api/upload/apply-bank-mapping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mapping: mapping, opening_balance: opBalVal })
      });

      const res = await resp.json();
      if (!res.success) {
        alert(`Error: ${res.error}`);
        return;
      }

      close();
      if (typeof AIAssistant !== 'undefined') AIAssistant.updateIngestionProgress(2);
      if (onMappingAppliedCallback) {
        onMappingAppliedCallback(res);
      }
    } catch (e) {
      alert(`Network error applying mapping: ${e.message}`);
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerText = 'Confirm & Process Statement';
    }
  }

  return {
    open,
    close,
    submitMapping
  };
})();
