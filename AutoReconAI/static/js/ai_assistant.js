/**
 * AutoReconAI - Multi-Agent AI Controller
 * (IngestionAuditorAI + SentinelRouterAI + ReconAuditorAI)
 * Manages resizable slide-over drawer, drag-to-expand width,
 * clean non-intrusive guardrail responses, and live Gemini pipeline.
 */

const AIAssistant = (() => {

  let isOpen = false;
  let isWide = false;
  let isDragging = false;
  let startX = 0;
  let startWidth = 480;

  async function init() {
    if (!document.getElementById('ai-copilot-drawer')) {
      try {
        const resp = await fetch('components/ai_copilot_drawer.html');
        if (resp.ok) {
          const html = await resp.text();
          const wrapper = document.createElement('div');
          wrapper.id = 'ai-component-wrapper';
          wrapper.innerHTML = html;
          document.body.appendChild(wrapper);
        }
      } catch (e) {
        console.error('Error loading AI component:', e);
      }
    }

    bindEvents();
    initResizer();
  }

  function bindEvents() {
    const btnToggle = document.getElementById('btn-toggle-ai-copilot');
    const btnClose = document.getElementById('btn-close-ai-drawer');
    const btnExpand = document.getElementById('btn-toggle-ai-expand');
    const chipAudit = document.getElementById('chip-ai-audit');
    const chipDispute = document.getElementById('chip-ai-dispute');
    const chipChargeback = document.getElementById('chip-ai-chargeback');
    const chipTax = document.getElementById('chip-ai-tax');
    const chipSummary = document.getElementById('chip-ai-summary');
    const btnSend = document.getElementById('btn-ai-send');
    const inputChat = document.getElementById('ai-chat-input');

    if (btnToggle) btnToggle.addEventListener('click', toggleDrawer);
    if (btnClose) btnClose.addEventListener('click', closeDrawer);
    if (btnExpand) btnExpand.addEventListener('click', toggleWideDrawer);

    if (chipAudit) chipAudit.addEventListener('click', () => askGeminiAI("Give me an itemized date-wise fee overcharges table with a total summary row at the bottom."));
    if (chipDispute) chipDispute.addEventListener('click', () => askGeminiAI("Draft a formal Razorpay Merchant Dispute Claim Ticket email for all fee overcharges found."));
    if (chipChargeback) chipChargeback.addEventListener('click', () => askGeminiAI("Show me details of customer dispute holds and bank chargebacks with required defense actions."));
    if (chipTax) chipTax.addEventListener('click', () => askGeminiAI("Provide a complete statutory tax audit covering Section 194-O TDS deductions and claimable GST Input Tax Credit (ITC)."));
    if (chipSummary) chipSummary.addEventListener('click', () => askGeminiAI("Provide a full financial recovery summary table of all mismatches grouped across all 5 edge cases."));

    if (btnSend && inputChat) {
      btnSend.addEventListener('click', handleCustomUserMessage);
      inputChat.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleCustomUserMessage();
      });
    }
  }

  function initResizer() {
    const resizer = document.getElementById('ai-drawer-resizer');
    const drawer = document.getElementById('ai-copilot-drawer');
    if (!resizer || !drawer) return;

    resizer.addEventListener('mousedown', (e) => {
      isDragging = true;
      startX = e.clientX;
      startWidth = drawer.getBoundingClientRect().width;
      drawer.classList.add('is-resizing');
      document.body.style.cursor = 'ew-resize';
      e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging || !drawer) return;
      const dx = startX - e.clientX;
      const newWidth = Math.min(Math.max(startWidth + dx, 380), window.innerWidth * 0.9);
      drawer.style.width = `${newWidth}px`;
      updateMainWrapperMargin(newWidth);
    });

    document.addEventListener('mouseup', () => {
      if (isDragging && drawer) {
        isDragging = false;
        drawer.classList.remove('is-resizing');
        document.body.style.cursor = '';
      }
    });
  }

  function toggleWideDrawer() {
    const drawer = document.getElementById('ai-copilot-drawer');
    if (!drawer) return;

    if (isWide) {
      drawer.style.width = '480px';
      isWide = false;
      updateMainWrapperMargin(480);
    } else {
      const wideWidth = Math.min(800, window.innerWidth * 0.75);
      drawer.style.width = `${wideWidth}px`;
      isWide = true;
      updateMainWrapperMargin(wideWidth);
    }
  }

  function updateMainWrapperMargin(drawerWidth) {
    const mainWrapper = document.querySelector('.main-wrapper');
    if (mainWrapper && document.body.classList.contains('ai-drawer-open')) {
      mainWrapper.style.maxWidth = `calc(100vw - 64px - ${drawerWidth}px)`;
      mainWrapper.style.width = `calc(100vw - 64px - ${drawerWidth}px)`;
    }
  }

  function toggleDrawer() {
    if (isOpen) {
      closeDrawer();
    } else {
      openDrawer();
    }
  }

  function openDrawer() {
    isOpen = true;
    const drawer = document.getElementById('ai-copilot-drawer');
    const body = document.body;

    if (drawer) {
      drawer.classList.add('open');
      const curWidth = drawer.getBoundingClientRect().width || 480;
      updateMainWrapperMargin(curWidth);
    }
    if (body) body.classList.add('ai-drawer-open');
  }

  function closeDrawer() {
    isOpen = false;
    const drawer = document.getElementById('ai-copilot-drawer');
    const body = document.body;
    const mainWrapper = document.querySelector('.main-wrapper');

    if (drawer) drawer.classList.remove('open');
    if (body) body.classList.remove('ai-drawer-open');
    if (mainWrapper) {
      mainWrapper.style.maxWidth = '';
      mainWrapper.style.width = '';
    }
  }

  async function askGeminiAI(userQuery) {
    appendUserMsg(userQuery);
    appendLoadingMsg("AI Agents analyzing reconciliation ledgers...");

    try {
      const resp = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userQuery })
      });

      const data = await resp.json();
      removeLoadingMsg();

      if (data.answer) {
        appendAIMsg(data.answer, data.pipeline);
      } else {
        appendAIMsg(`⚠️ ${data.error || 'Unable to get response from AI Agents.'}`);
      }
    } catch (e) {
      removeLoadingMsg();
      appendAIMsg(`⚠️ Connection error: ${e.message}`);
    }
  }

  function handleCustomUserMessage() {
    const input = document.getElementById('ai-chat-input');
    if (!input || !input.value.trim()) return;

    const query = input.value.trim();
    input.value = '';
    askGeminiAI(query);
  }

  function appendUserMsg(msg) {
    const chatFeed = document.getElementById('ai-chat-feed');
    const div = document.createElement('div');
    div.className = 'user-msg-box';
    div.innerText = msg;
    chatFeed.appendChild(div);
    scrollToBottom();
  }

  function appendAIMsg(rawText, pipeline) {
    const chatFeed = document.getElementById('ai-chat-feed');
    const div = document.createElement('div');
    div.className = 'ai-msg-box';

    let pipelineHtml = '';
    if (pipeline) {
      const a1 = pipeline.agent_1 || pipeline.agent_0 || {};
      const a2 = pipeline.agent_2 || pipeline.agent_1 || {};
      const a3 = pipeline.agent_3 || pipeline.agent_4 || {};

      // If blocked or out of scope: NO alert badges at all, keep it completely clean!
      if (a1.scope === 'BLOCKED' || a1.status === 'INJECTION_BLOCKED' || a2.scope === 'OUT_OF_SCOPE' || a1.scope === 'OUT_OF_SCOPE') {
        pipelineHtml = '';
      } else if (a1.status === 'DATA_REQUIRED' || a2.status === 'DATA_REQUIRED') {
        pipelineHtml = `
          <div class="pipeline-badge-container">
            <div class="agent-pill agent-pill-router">📁 Agent 1 (SentinelFirewallAI): Data Ingestion Required</div>
          </div>
        `;
      } else {
        const a1Badge = `<div class="agent-pill agent-pill-router">🛡️ Agent 1 (SentinelFirewallAI): Security Cleared</div>`;

        let toolsDetailHtml = '';
        const toolsCalled = a2.tools_called || [];
        const dataSources = a2.data_sources || [];
        const dataSourcesStr = dataSources.length > 0 ? dataSources.join(', ') : 'Store Orders CSV, Settlement Payouts CSV, Bank Statement';
        if (toolsCalled.length > 0) {
          const toolNames = toolsCalled.map(t => typeof t === 'object' ? `<code>${t.tool}()</code>` : `<code>${t}()</code>`).join(', ');
          toolsDetailHtml = `<div class="agent-pill-details"><span class="pill-detail-label">⚙️ Executed Tools:</span> ${toolNames} <span class="pill-detail-sep">•</span> <span class="pill-detail-label">📁 Data Sources:</span> ${dataSourcesStr}</div>`;
        }

        const a2Badge = `
          <div class="agent-pill-block">
            <div class="agent-pill agent-pill-router">🧠 Agent 2 (DomainReasonerAI): Autonomous ReAct Auditor</div>
            ${toolsDetailHtml}
          </div>
        `;

        const a3StatusText = (a3.status || 'TAG_ALIGNED_SYNTHESIS').replace(/_/g, ' ');
        const a3Badge = `<div class="agent-pill agent-pill-auditor">✍️ Agent 3 (PrecisionSynthesizerAI): ${a3StatusText}</div>`;

        pipelineHtml = `
          <div class="pipeline-badge-container">
            ${a1Badge}
            ${a2Badge}
            ${a3Badge}
          </div>
        `;
      }
    }

    const formattedContent = formatMarkdown(rawText);

    let copyBtnHtml = '';
    if (rawText.includes("merchant-disputes@") || rawText.includes("Dispute Claim")) {
      copyBtnHtml = `<div style="margin-top: 10px; text-align: right;"><button class="btn-copy-dispute" onclick="navigator.clipboard.writeText(this.getAttribute('data-raw')); this.innerText='✅ Copied to Clipboard!';" data-raw="${rawText.replace(/"/g, '&quot;')}" style="background: #2563eb; color: white; border: none; padding: 6px 14px; border-radius: 6px; font-size: 0.82rem; cursor: pointer; font-weight: 600; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">📋 Copy Dispute Email</button></div>`;
    }

    div.innerHTML = `
      <div class="ai-bot-avatar">🤖</div>
      <div class="ai-msg-content">
        ${pipelineHtml}
        <div>${formattedContent}</div>
        ${copyBtnHtml}
      </div>
    `;
    chatFeed.appendChild(div);
    
    // Automatically render any Mermaid diagrams
    if (window.mermaid && div.querySelector('.mermaid')) {
      setTimeout(() => {
        try {
          mermaid.run({ nodes: div.querySelectorAll('.mermaid') });
        } catch (err) {
          try {
            mermaid.init(undefined, div.querySelectorAll('.mermaid'));
          } catch (e2) {
            console.warn('Mermaid render warning:', e2);
          }
        }
      }, 50);
    }

    scrollToBottom();
  }

  function appendLoadingMsg(text) {
    const chatFeed = document.getElementById('ai-chat-feed');
    const div = document.createElement('div');
    div.id = 'ai-loading-indicator';
    div.className = 'ai-msg-box';
    div.innerHTML = `
      <div class="ai-bot-avatar spinning">⚡</div>
      <div class="ai-msg-content" style="color: var(--text-secondary); font-style: italic;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span>${text}</span>
        </div>
      </div>
    `;
    chatFeed.appendChild(div);
    scrollToBottom();
  }

  function removeLoadingMsg() {
    const el = document.getElementById('ai-loading-indicator');
    if (el) el.remove();
  }

  function scrollToBottom() {
    const chatFeed = document.getElementById('ai-chat-feed');
    if (chatFeed) chatFeed.scrollTop = chatFeed.scrollHeight;
  }

  function updateIngestionProgress(uploadedCount) {
    if (uploadedCount === 1) {
      appendAIMsg("🎉 Store Orders CSV loaded cleanly! Next, upload your Bank Statement (PDF or Excel) in Step 2.");
    } else if (uploadedCount === 2) {
      appendAIMsg("📄 Bank Statement mapped perfectly! Finally, upload your Razorpay Settlement CSV in Step 3.");
    } else if (uploadedCount === 3) {
      appendAIMsg("🚀 All 3 financial files uploaded and mapped! Click the 'Proceed to 3-Way Reconciliation' button above to view your matrix!");
    }
  }

  function updateReconStatus(mismatchedCount) {
    if (mismatchedCount === 0) {
      appendAIMsg("Hurray! 🎉 Congrats, 100% of your customer orders match payment gateway credits and bank deposits perfectly to the exact paise!");
    } else {
      appendAIMsg(`🚨 Reconciliation audit detected ${mismatchedCount} mismatched orders in your reconciliation batch. Select a question above or type any query to audit!`);
    }
  }

  function formatMarkdown(text) {
    if (!text) return "";

    const mermaidBlocks = [];
    const codeBlocks = [];

    // 1. Stash Mermaid blocks
    let processed = text.replace(/```mermaid([\s\S]*?)```/gi, (match, code) => {
      const id = mermaidBlocks.length;
      mermaidBlocks.push(code.trim());
      return `\n\n@@MERMAID_${id}@@\n\n`;
    });

    // 2. Stash other code blocks
    processed = processed.replace(/```(?:text|plain)?([\s\S]*?)```/gi, (match, code) => {
      const id = codeBlocks.length;
      codeBlocks.push(code.trim());
      return `\n\n@@CODE_${id}@@\n\n`;
    });

    // 3. Parse Markdown tables
    const lines = processed.split('\n');
    let inTable = false;
    let tableHtml = '';
    let processedLines = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      if (line.startsWith('|') && line.endsWith('|')) {
        if (!inTable) {
          inTable = true;
          tableHtml = '<table>';
          const headers = line.split('|').filter(c => c.trim() !== '');
          tableHtml += '<thead><tr>' + headers.map(h => `<th>${formatInline(h.trim())}</th>`).join('') + '</tr></thead><tbody>';
        } else if (line.includes('---')) {
          // Separator line, ignore
        } else {
          const cells = line.split('|').filter(c => c.trim() !== '');
          tableHtml += '<tr>' + cells.map(c => `<td>${formatInline(c.trim())}</td>`).join('') + '</tr>';
        }
      } else {
        if (inTable) {
          inTable = false;
          tableHtml += '</tbody></table>';
          processedLines.push(tableHtml);
          tableHtml = '';
        }
        processedLines.push(line);
      }
    }

    if (inTable) {
      tableHtml += '</tbody></table>';
      processedLines.push(tableHtml);
    }

    let joined = processedLines.join('\n');

    // Headings
    joined = joined.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    joined = joined.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    joined = joined.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    joined = joined.replace(/^---$/gim, '<hr/>');

    // Lists
    joined = joined.replace(/^\* (.*$)/gim, '<li>$1</li>');
    joined = joined.replace(/^- (.*$)/gim, '<li>$1</li>');

    // Paragraphs / Newlines
    joined = joined.replace(/\n\n/g, '<br/><br/>');
    joined = joined.replace(/\n/g, '<br/>');

    joined = formatInline(joined);

    // 4. Restore code blocks & Mermaid blocks cleanly without any <br> contamination
    codeBlocks.forEach((code, i) => {
      const html = `<pre style="background: #0f172a; color: #f8fafc; padding: 12px 14px; border-radius: 6px; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; overflow-x: auto; margin: 10px 0; line-height: 1.45;">${code}</pre>`;
      joined = joined.replace(new RegExp(`@@CODE_${i}@@`, 'g'), html);
    });

    mermaidBlocks.forEach((code, i) => {
      const html = `<div class="mermaid-wrapper" style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 12px 0; overflow-x: auto; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center;"><pre class="mermaid" style="margin: 0; font-family: sans-serif;">${code}</pre></div>`;
      joined = joined.replace(new RegExp(`@@MERMAID_${i}@@`, 'g'), html);
    });

    // Clean up extraneous breaks around HTML chart/div tags
    joined = joined.replace(/<br\s*[\/]?>\s*(<div class="mermaid-wrapper"|<pre)/gi, '$1');
    joined = joined.replace(/(<\/div>|<\/pre>)\s*<br\s*[\/]?>/gi, '$1');

    return joined;
  }

  function formatInline(str) {
    return str
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  }

  function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
      alert("📋 Content copied to clipboard!");
    }).catch(err => {
      console.error('Failed to copy: ', err);
    });
  }

  return {
    init,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    askGeminiAI,
    updateIngestionProgress,
    updateReconStatus,
    copyToClipboard
  };

})();
