# LatentPay — Cognitive Payment Intelligence

> **Pine Labs AI Hackathon 2026** · Theme: Agentic / Autonomous Commerce & Intelligent Payments

LatentPay is a secure, AI-native payment security layer that sits between autonomous AI agents (OpenClaw, PicoClaw) and Pine Labs payment infrastructure. Agents can make payments without ever touching your real bank account, UPI, or cards.

---

## The Problem

AI agents can now browse, email, order food, and manage files autonomously. But when they need to **pay for something**, there is no safe way to do it. Giving an agent your UPI or card details is a security disaster — one compromised prompt and your bank account is exposed.

## The Solution

LatentPay introduces a **Pine Labs Agent Wallet**:

- The user loads a fixed balance into a Pine Labs-controlled wallet (one-time human action)
- The agent only ever sees and spends from this wallet — **zero knowledge of your real bank, UPI, or cards**
- Every payment attempt is intercepted and analysed before a single rupee moves
- Suspicious payments go to a human for approval via Telegram
- Critical threats trigger an instant wallet freeze — your real money stays safe

---

## Architecture

```
User's Real Money (UPI / Cards)
        │
        │ manual top-up only
        ▼
Pine Labs Agent Wallet ←── fixed balance, spend limits
        │
        │ every payment request
        ▼
┌─────────────────────────────────────────┐
│           LatentPay Core                │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Merchant │ │   ML     │ │ Policy  │ │
│  │  Check   │ │ Behavior │ │ Engine  │ │
│  └────┬─────┘ └────┬─────┘ └────┬────┘ │
│       └────────────┼─────────────┘      │
│               Risk Engine               │
└────────┬────────────────────┬───────────┘
         │ suspicious         │ clear
         ▼                    ▼
  Telegram HITL         Pine Labs Order
  Approve / Kill        (Blinkit, Amazon…)
         │
    Kill →  Death Switch (wallet frozen, Redis broadcast)
```

---

## Features

| Feature | Description |
|---------|-------------|
| 🛡️ **Intelligent Interception** | 3 parallel checks: merchant trust (VirusTotal), ML behaviour analysis (Isolation Forest), policy rules |
| 🤖 **AI Threat Hunter** | Gemini-powered log analyst scans for attack patterns, amount probing, merchant hopping |
| ⚡ **Kill Switch** | One tap freezes wallet globally via Redis pub/sub across all agent instances |
| 👤 **Human-in-the-Loop** | Suspicious payments pause and fire a Telegram alert; 5-minute timeout auto-kills |
| 🔗 **Tamper-Proof Ledger** | SHA-256 hash chain across dual independent databases (PostgreSQL + immutable SQLite) |
| 🧠 **Spend Intelligence** | Detects unused subscriptions, price hikes, and projects monthly budgets |
| 📊 **Real-Time Dashboard** | React dashboard with live transaction feed, risk scores, and audit log explorer |

---

## Demo Scenario

Every Sunday at 8am, the agent:

1. Activates camera → scans kitchen via vision model
2. LLM builds a structured grocery list
3. LatentPay intercepts the Blinkit payment request
4. 3 checks run in parallel (< 200ms)
5. **If clear** → Pine Labs `createOrder` → groceries ordered
6. **If suspicious** → Telegram alert → user approves or kills
7. **If critical** → Kill switch fires instantly, wallet frozen, real money untouched

---

## Project Structure

```
sentinelpay/
├── backend/                    # FastAPI Python backend
│   ├── main.py
│   ├── wallet/                 # Wallet management, balance, freeze
│   ├── security/               # Interceptor, merchant check, ML engine, policy
│   ├── pinelabs/               # Pine Labs API wrapper (UAT + production)
│   ├── hitl/                   # Telegram human-in-the-loop approval flow
│   ├── death_switch/           # Global wallet freeze + Redis pub/sub
│   ├── intelligence/           # Spend analysis, forecasts, subscription detection
│   └── logging/                # Hash chain, dual-store logger, AI analyst, verifier
│
├── agent-skills/
│   ├── openclaw/pinepay.js     # OpenClaw payment skill (JavaScript)
│   └── picoclaw/pinepay.go     # PicoClaw payment skill (Go — runs on $10 Sipeed board)
│
├── dashboard/                  # React frontend (LatentPay UI)
│   ├── public/
│   └── src/App.js              # Full dashboard — wallet, transactions, risk, ledger, threats
│
├── ml/
│   ├── anomaly_model.py        # Isolation Forest anomaly detection
│   ├── baseline_builder.py     # Per-user spend baseline
│   └── adaptive_learner.py     # Online learning — updates after every safe tx
│
├── docker-compose.yml
└── .env.example
```

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Pine Labs UAT credentials ([register here](https://dashboardv2.pluralonline.com/signup))
- Telegram bot token (via [@BotFather](https://t.me/BotFather))
- Gemini API key ([Google AI Studio](https://aistudio.google.com))
- VirusTotal API key (free tier at [virustotal.com](https://virustotal.com))

### Setup

```bash
git clone https://github.com/DebasishTripathy13/pinelab-project.git
cd pinelab-project

# Copy and fill in your credentials
cp .env.example .env
# Edit .env with your API keys

# Start everything
docker-compose up
```

Dashboard available at: **http://localhost:3000**  
Backend API at: **http://localhost:8000/docs**

### Run Dashboard Only (development)

```bash
cd dashboard
npm install
npm start
```

---

## Environment Variables

See [`.env.example`](.env.example) for all required variables:

```env
PINE_CLIENT_ID=          # Pine Labs UAT client ID
PINE_CLIENT_SECRET=      # Pine Labs UAT client secret
TELEGRAM_BOT_TOKEN=      # Telegram bot token from @BotFather
VIRUSTOTAL_API_KEY=      # VirusTotal API key (free tier)
GEMINI_API_KEY=          # Google Gemini API key
OPENAI_API_KEY=          # Optional OpenAI fallback
AI_ANALYST_BACKEND=gemini  # gemini | openai | ollama
```

---

## Agent Skills

### OpenClaw (JavaScript)

Drop `agent-skills/openclaw/pinepay.js` into your OpenClaw skills folder and set:

```env
SENTINELPAY_URL=http://localhost:8000
SENTINELPAY_AGENT_TOKEN=your-token
OPENCLAW_AGENT_ID=openclaw-01
```

The agent can now say: *"Order groceries from Blinkit for ₹500"* and the full payment security pipeline runs automatically.

### PicoClaw (Go — hardware)

Runs on a [$10 Sipeed LicheeRV-Nano](https://github.com/sipeed/picoclaw). Compile and configure `agent-skills/picoclaw/pinepay.go`.

---

## Security Design

- **Wallet isolation** — agent token only grants spend permission; no access to real payment credentials
- **Pine Labs as custodian** — LatentPay never holds funds; Pine Labs holds the wallet balance
- **Redis kill broadcast** — death switch fires across ALL agent instances simultaneously
- **5-minute HITL timeout** — no human response = automatic kill (safe by default)
- **Dual-store log integrity** — SHA-256 hash chain across PostgreSQL + append-only SQLite; tampering breaks the chain instantly
- **AI analyst PII sanitization** — wallet IDs and user IDs stripped before any external LLM call
- **Ollama local mode** — fully offline threat analysis, zero data leaves the machine

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python, PostgreSQL, Redis, SQLite |
| Frontend | React, Recharts, Tailwind CSS |
| ML | Scikit-learn (Isolation Forest), adaptive online learning |
| AI Analyst | Gemini 2.0 Flash / GPT-4o / Llama 3.1 (Ollama) |
| Payments | Pine Labs Agent Toolkit, Pine Labs UAT API |
| Messaging | python-telegram-bot |
| Infra | Docker Compose |

---

## Hackathon

**Built for Pine Labs AI Hackathon — March 14, 2026**  
Theme: *Agentic / Autonomous Commerce & Intelligent Payments*

🏅 **Result:** Won **3rd Place** in the Pine Labs Playground AI Hackathon

Team: DebasishTripathy13
