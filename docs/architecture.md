# 🏗️ System Architecture & Service Network

AutoReconAI operates as a multi-tier reconciliation ecosystem coordinating three isolated local service layers:

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor': '#0f172a', 'edgeLabelBackground':'#1e293b', 'tertiaryColor': '#1e293b'}}}%%
flowchart TD
    subgraph S1["🛒 Merchant E-Commerce Domain (Port 5050)"]
        A1["Storefront Frontend<br/><code>http://127.0.0.1:5050</code>"]
        A2["Storefront Flask API<br/><code>backend.py</code>"]
        A3[("SQLite Database<br/><code>store.db</code><br/><i>products, orders, cart</i>")]
        A1 <-->|"REST APIs"| A2
        A2 <-->|"SQL Operations"| A3
    end

    subgraph S2["💳 Payment Gateway Domain (Port 5051)"]
        B1["Razorpay Gateway Mock<br/><code>AutoReconAI/backend/gateway_server.py</code>"]
        B2[("SQLite Database<br/><code>store.db</code><br/><i>payments ledger</i>")]
        B1 <-->|"Ledger Mutex Writes"| B2
    end

    subgraph S3["🏛️ AutoReconAI Platform & AI Engine (Port 5055)"]
        C1["Reconciliation Hub UI<br/><code>http://127.0.0.1:5055</code>"]
        C2["Recon Engine & AI Orchestrator<br/><code>AutoReconAI/backend/app.py</code>"]
        C3["Multi-Stage AI Pipeline<br/><code>SentinelFirewall + DomainReasoner + Synthesizer</code>"]
        C4["ReconToolbox<br/><i>(10 Python Auditing Tools)</i>"]
        C1 <-->|"Interactive Workspaces"| C2
        C2 <-->|"Context Grounding"| C3
        C3 <-->|"Native Function Calls"| C4
    end

    A2 -->|"1. Forward Checkout"| B1
    B1 -->|"2. Webhook Callback (Captures or Drops)"| A2
    C2 -.->|"Read Only Audit"| A3
    C2 -.->|"Read Only Audit"| B2

    classDef storeStyle fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef gateStyle fill:#1e1b4b,stroke:#818cf8,stroke-width:2px,color:#ffffff;
    classDef reconStyle fill:#022c22,stroke:#34d399,stroke-width:2px,color:#ffffff;

    class A1,A2,A3 storeStyle;
    class B1,B2 gateStyle;
    class C1,C2,C3,C4 reconStyle;
```

---

## 🌐 Port Map & Network Protocol

| Service Component | Port | Protocol | Primary Responsibilities |
|:---|:---|:---|:---|
| **Merchant Storefront (`FreshMart`)** | `5050` | HTTP / JSON | Product catalog browsing, cart operations, customer checkout sessions, and local order creation (`PENDING` -> `FULFILLED`). |
| **Razorpay Payment Engine Mock** | `5051` | HTTP / JSON | Payment authorization, webhook emissions, settlement UTR batch bundling, and fee/tax/TDS calculations. |
| **AutoReconAI Reconciliation Hub** | `5055` | HTTP / SSE / REST | 3-way reconciliation matrix, bank statement PDF parsing, Chart.js analytics dashboard, and the multi-stage agentic AI copilot. |

---

## 🔄 End-to-End Simulation Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Customer as 🛒 Customer Shopping Simulator
    participant Store as 🏬 Merchant Storefront (Port 5050)
    participant Gateway as 💳 Razorpay Engine (Port 5051)
    participant Bank as 🏦 Bank Statement Generator
    participant Hub as ⚡ AutoReconAI Platform (Port 5055)
    participant AI as 🧠 Multi-Stage AI Pipeline

    Customer->>Store: Add grocery items & trigger checkout
    Store->>Store: Create order record (Status: PENDING)
    Store->>Gateway: Forward payment request (Amount, Order ID)
    Gateway->>Gateway: Authorize card/UPI payment & deduct contracted MDR + GST
    
    alt Standard Transaction (100% Reconciled)
        Gateway-->>Store: POST /api/webhook/razorpay (Payment Captured)
        Store->>Store: Mark order as FULFILLED
        Gateway->>Bank: Credit net settlement lumped under daily UTR
    else Controlled Anomaly: Dropped Webhook
        Gateway-xStore: Simulated packet drop (Webhook never reaches Store)
        Store->>Store: Order remains stuck in PENDING status
        Gateway->>Bank: Credit net settlement to bank anyway under UTR
    else Controlled Anomaly: Fee Overcharge
        Gateway->>Gateway: Bill inflated interchange fee (~2.75% vs 2.0% SLA)
        Gateway->>Bank: Credit reduced net payout to bank
    end

    Customer->>Bank: Generate digital bank PDF with operational debits
    Bank-->>Hub: Ingest store_orders.csv, razorpay_settlement_recon.csv, bank_statement.pdf
    Hub->>Hub: Triangulate 3-way UTR ledger & flag anomalies
    Hub->>AI: User asks: "Explain why ORD_1025 is mismatched"
    AI->>AI: Deterministic tool execution via ReconToolbox
    AI-->>Hub: Grounded forensic explanation & ready-to-send dispute ticket
```
