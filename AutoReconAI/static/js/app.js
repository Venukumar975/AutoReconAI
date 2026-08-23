/**
 * AutoReconAI - Main Application Controller & View Router
 * Manages view switching between File Ingestion & 3-Way Reconciliation Matrix.
 */

const App = (() => {

  function init() {
    Uploader.init();
    checkServerStatus();

    // Reset Session
    document.getElementById('btn-reset-session').addEventListener('click', handleResetSession);

    // Proceed to Reconciliation Action (Center Button on Ingestion page)
    document.getElementById('btn-proceed-recon').addEventListener('click', proceedToReconciliation);

    // Sidebar Navigation Switching
    document.getElementById('nav-ingestion').addEventListener('click', () => switchView('ingestion'));
    document.getElementById('nav-recon').addEventListener('click', () => {
      const navRecon = document.getElementById('nav-recon');
      if (!navRecon.classList.contains('disabled')) {
        proceedToReconciliation();
      }
    });

    // Mapping Modal Handlers
    document.getElementById('btn-close-mapping-modal').addEventListener('click', MapperModal.close);
    document.getElementById('btn-cancel-mapping').addEventListener('click', MapperModal.close);
    document.getElementById('btn-apply-mapping').addEventListener('click', MapperModal.submitMapping);
  }

  function switchView(viewName) {
    const viewIngestion = document.getElementById('view-ingestion');
    const viewRecon = document.getElementById('view-recon');
    const navIngestion = document.getElementById('nav-ingestion');
    const navRecon = document.getElementById('nav-recon');
    const breadcrumbCurrent = document.getElementById('breadcrumb-current-text');

    if (viewName === 'ingestion') {
      viewIngestion.classList.remove('hidden-view');
      viewRecon.classList.add('hidden-view');

      navIngestion.classList.add('active');
      navRecon.classList.remove('active');
      if (breadcrumbCurrent) breadcrumbCurrent.innerText = 'Sequential File Ingestion & Mapping';
    } else if (viewName === 'recon') {
      viewIngestion.classList.add('hidden-view');
      viewRecon.classList.remove('hidden-view');

      navIngestion.classList.remove('active');
      navRecon.classList.add('active');
      if (breadcrumbCurrent) breadcrumbCurrent.innerText = '3-Way Reconciliation & UTR Container Matrix';
    }
  }

  async function checkServerStatus() {
    try {
      const resp = await fetch('/api/status');
      const data = await resp.json();
      if (data.status === 'online') {
        document.getElementById('status-indicator-text').innerText = 'Backend Connected';
        document.getElementById('status-indicator-sub').innerText = `Port ${data.port} Online`;
      }
    } catch (e) {
      document.getElementById('status-indicator-text').innerText = 'Connecting...';
    }
  }

  async function checkPipelineReady() {
    try {
      const resp = await fetch('/api/status');
      const data = await resp.json();
      const state = data.session_state;

      const proceedBtn = document.getElementById('btn-proceed-recon');
      const proceedSubtext = document.getElementById('proceed-subtext');
      const navRecon = document.getElementById('nav-recon');

      if (state.has_orders && state.has_bank_statement && state.has_settlement) {
        proceedBtn.disabled = false;
        proceedSubtext.innerText = '✅ All 3 files uploaded & verified. Click to inspect the 3-Way Reconciliation Matrix!';
        proceedSubtext.style.color = 'var(--accent-green)';
        
        // Unlock sidebar tab
        navRecon.classList.remove('disabled');
        navRecon.querySelector('.nav-badge').innerText = 'Ready';
        navRecon.querySelector('.nav-badge').style.backgroundColor = 'var(--accent-green)';
        navRecon.querySelector('.nav-badge').style.color = '#ffffff';
      } else {
        proceedBtn.disabled = true;
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function proceedToReconciliation() {
    const btn = document.getElementById('btn-proceed-recon');
    btn.disabled = true;
    btn.innerText = '⚡ Synthesizing UTR Grouped Matrix...';

    try {
      const resp = await fetch('/api/generate-linked-grid');
      const data = await resp.json();

      if (!data.success) {
        alert(`Error: ${data.error}`);
        btn.disabled = false;
        btn.innerText = '🚀 Proceed to 3-Way Reconciliation Matrix';
        return;
      }

      VisualLinks.renderGroupedUTRMatrix(data);
      switchView('recon');

      btn.disabled = false;
      btn.innerText = '🚀 Proceed to 3-Way Reconciliation Matrix';

    } catch (e) {
      alert(`Network error generating reconciliation matrix: ${e.message}`);
      btn.disabled = false;
      btn.innerText = '🚀 Proceed to 3-Way Reconciliation Matrix';
    }
  }

  async function handleResetSession() {
    if (!confirm('Are you sure you want to reset all uploaded data and start fresh?')) {
      return;
    }

    try {
      await fetch('/api/session/reset', { method: 'POST' });
      window.location.reload();
    } catch (e) {
      alert('Error resetting session');
    }
  }

  return {
    init,
    checkPipelineReady,
    switchView
  };
})();

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
