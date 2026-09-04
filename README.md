# PehraPay — AI Commerce & Trust Layer for Autonomous Payments

> **Track 01: AI Growth & Agentic Commerce** (Razorpay AI Hackathon)  
> ⚠️ **RAZORPAY TEST MODE ONLY**: PehraPay operates strictly against Razorpay Test-Mode APIs (`rzp_test_*`). No real currency or live card transactions are executed.

---

### The One-Line Reality
**PehraPay** sits between autonomous AI buyer agents and Razorpay merchants. It gives merchants an AI-discoverable catalog, drives revenue through constraint-aware cross-sells, and uses a deterministic, HMAC-signed policy engine to prevent LLM hallucinations, budget overruns, and rogue purchases before any money moves.

---

## 🛑 Why Autonomous Agents Need a Trust Layer

Autonomous AI agents equipped with direct payment credentials or raw API keys fail in production for four predictable reasons:

1. **Prompt Injection Hijacks**: Malicious product reviews or poisoned product descriptions can instruct the agent to ignore user instructions and purchase unrelated goods.
2. **Price & Merchant Hallucination**: LLMs generate realistic-looking prices and will accept unverified merchant IDs without a canonical registry.
3. **Runaway Loops & Budget Drain**: A minor software bug or retry loop can fire 50 rapid transactions in seconds, exhausting spending pools before human intervention.
4. **Zero Pre-Execution Auditability**: Once a raw API key makes an authorized call, the funds are committed. There is no cryptographic record of what policy was checked or why.

PehraPay resolves these issues by treating the LLM strictly as an **intent parser**, never an authorizer. The canonical catalog, policy engine, and Razorpay gateway calls exist outside the model's control boundary.

---

## 🏗️ End-to-End Pipeline Architecture

```
                  ┌─────────────────────────────────────────────────────────┐
                  │                    USER INSTRUCTION                     │
                  │       "Find me a good morning drink under ₹1,000"       │
                  └────────────────────────────┬────────────────────────────┘
                                               │
                                               v
    ┌─────────────────────────────────────────────────────────────────────────────────────┐
    │ STAGE 1: 🤖 Intent Parsing (Gemini + Constraint-Aware Fallback Parser)              │
    │  - Extracts unstructured request into: Item, Quantity, Price Ceiling                │
    │  - On quota exhaustion or network loss, falls back to constraint-aware local parser │
    │    that cleanly isolates price limits from quantity counts                          │
    └──────────────────────────────────────────┬──────────────────────────────────────────┘
                                               │
                                               v
    ┌─────────────────────────────────────────────────────────────────────────────────────┐
    │ STAGE 2: 📦 PehraPay Catalog & Goal Resolver (Authoritative Source of Truth)        │
    │  - Overwrites LLM hallucinated prices and merchant IDs with database records        │
    │  - Goal Discovery: Resolves generic queries to highest-trust matching merchant item │
    │  - Cross-Sell Engine: Finds relevant alternatives within remaining mandate budget   │
    └──────────────────────────────────────────┬──────────────────────────────────────────┘
                                               │
                                               v
    ┌─────────────────────────────────────────────────────────────────────────────────────┐
    │ STAGE 3: ⚖️ Deterministic Policy Engine (6 Hard Rule Checks)                         │
    │  1. HMAC-SHA256 Signature Integrity    4. Merchant Category Whitelist               │
    │  2. Mandate Expiry Timestamp           5. Minimum Merchant Trust Score (1.0 - 5.0)  │
    │  3. Max Transaction Count Limit        6. Cumulative Budget Cap & Risk Threshold    │
    └──────────────────────────────────────────┬──────────────────────────────────────────┘
                                               │
              ┌────────────────────────────────┼────────────────────────────────┐
              │                                │                                │
        [ 🛡️ APPROVE ]                  [ ⚠️ HUMAN_REVIEW ]              [ 🛑 REJECT ]
              │                                │                                │
              v                                v                                v
    ┌────────────────────┐           ┌───────────────────┐            ┌───────────────────┐
    │ 💳 Razorpay Order  │           │ ⚠️ Order Suspended│            │ 🔒 Execution      │
    │  - Order Created   │           │  - Flags for      │            │    Halted         │
    │  - Payment Link    │           │    confirmation   │            │  - Zero Gateway   │
    │  - Status:         │           │  - Status:        │            │    Touchpoints    │
    │    AUTHORIZED      │           │    SUSPENDED      │            │  - Status: BLOCKED│
    └─────────┬──────────┘           └───────────────────┘            └───────────────────┘
              │
              v
    ┌─────────────────────────────────────────────────────────────────────────────────────┐
    │ STAGE 4: ⚡ Settlement Loop (Razorpay Webhook Handler)                               │
    │  - Receives order.paid / payment.captured webhooks                                  │
    │  - Verifies order existence in SQLite audit store                                   │
    │  - Transitions status from AUTHORIZED to PAID_SETTLED                               │
    │  - Idempotent: safe against duplicate webhook deliveries without double-counting    │
    └─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔌 Integration: How AI Agents Call PehraPay

PehraPay exposes a REST API and a lightweight Python Agent SDK for agent frameworks like LangChain, CrewAI, AutoGen, or LlamaIndex.

### 1. REST API Surface

#### **Endpoint**: `POST /api/purchase`
Executes natural-language requests against a signed mandate.

```bash
curl -X POST http://127.0.0.1:8000/api/purchase \
  -H "Content-Type: application/json" \
  -d '{
    "mandate_id": "mandate_coffee",
    "buyer_request": "buy 1 box of organic green tea",
    "is_recommendation_accepted": false
  }'
```

#### **Approved Response Example (`decision: "APPROVE"`):**
```json
{
  "intent": {
    "item": "Organic Green Tea (50 bags)",
    "price": 450.0,
    "quantity": 1,
    "merchant_id": "merch_nature_choice"
  },
  "product_category": "groceries",
  "merchant_trust_level": 3.5,
  "decision": "APPROVE",
  "reason": "Transaction meets all mandate requirements",
  "order_id": "order_TXfkxL1l4lxyD2",
  "status": "AUTHORIZED",
  "razorpay_url": "https://rzp.io/i/mock_order_TXfkxL1l4lxyD2",
  "fallback_active": false,
  "razorpay_fallback_active": false,
  "request_id": "8c593649514b8a...",
  "idempotent_replay": false,
  "goal_resolution_notes": null,
  "recommendation": {
    "item": "Premium Arabica Coffee Beans (1kg)",
    "price": 1200.0,
    "merchant_trust_level": 4.8,
    "reason": "Also in groceries · ₹1200 · trust 4.8/5 · within your remaining mandate budget"
  }
}
```

---

### 2. Settlement Webhook: `POST /api/webhooks/razorpay`

Judges frequently ask: *"What happens after the buyer pays?"*

PehraPay handles this with an idempotent settlement webhook endpoint that processes simulated or real Razorpay webhook payloads (`order.paid` / `payment.captured`).

```bash
curl -X POST http://127.0.0.1:8000/api/webhooks/razorpay \
  -H "Content-Type: application/json" \
  -d '{
    "event": "payment.captured",
    "order_id": "order_TXfkxL1l4lxyD2",
    "payment_id": "pay_test_1788462169"
  }'
```

**Settlement Response:**
```json
{
  "status": "success",
  "event": "payment.captured",
  "order_id": "order_TXfkxL1l4lxyD2",
  "payment_id": "pay_test_1788462169",
  "transaction_status": "PAID_SETTLED",
  "settled_at": 1788462170,
  "mandate_id": "mandate_coffee",
  "amount": 450.0
}
```

> **Budget Timing Architecture**: Budget reservation occurs at **Authorization time** (`decision == "APPROVE"`), calculated via `store.get_spent_amount()`. This prevents concurrent agent requests from exceeding the cumulative cap before settlement finishes. When the webhook settles the transaction, the state flips to `PAID_SETTLED` without double-deducting remaining budget.

---

### 3. Python Agent Client SDK (`backend/pehrapay_client.py`)

External autonomous agents can integrate directly using the clean Python wrapper:

```python
from backend.pehrapay_client import PehraPayAgentClient

client = PehraPayAgentClient(api_base="http://127.0.0.1:8000")

# 1. Discover verified merchant products
catalog = client.get_catalog()
print(f"Discovered {len(catalog)} verified merchant items.")

# 2. Execute bounded purchase
result = client.purchase(
    mandate_id="mandate_coffee",
    buyer_request="buy me morning coffee under ₹1000"
)

if result["decision"] == "APPROVE":
    print(f"Authorized Order: {result['order_id']}")
    print(f"Razorpay Link: {result['razorpay_url']}")
    
    # 3. Simulate customer checkout settlement
    settlement = client.settle_payment(order_id=result["order_id"])
    print(f"Status: {settlement['transaction_status']}")
```

---

## 🌟 Key Features

### 🏪 1. AI-Readable Merchant Catalog (`GET /api/catalog`)
Merchants publish structured catalogs with trust levels, category classification, verified badges, and fixed prices. Autonomous AI buyers can inspect and query this endpoint directly rather than scraping brittle HTML product pages.

### 🎯 2. Goal-Based Product Resolver
When users give broad or non-exact instructions (*"find me coffee under ₹1000"* or *"something for breakfast under ₹500"*), PehraPay doesn't perform naive keyword guessing. Both the live Gemini parser and local fallback parser feed into the same deterministic resolver:
- Extracts price ceilings while isolating them from quantities.
- Identifies the intended merchant category via canonical keyword maps.
- Strictly filters out out-of-category items (e.g. kitchenware mugs are excluded from groceries coffee requests).
- Filters candidates by remaining mandate budget and price ceiling.
- Prioritizes specific item keywords within the category (e.g. distinguishing tea vs coffee).
- Deterministically selects the candidate with the **highest Merchant Trust Score**, logging the exact resolution rationale.

### 💡 3. Constraint-Safe In-Mandate Cross-Sells & 1-Click Switch
After authorizing a purchase, PehraPay inspects remaining mandate budget and category constraints to suggest high-trust alternatives. In the dashboard, clicking **"🔄 Accept & Switch to Recommended Item"** immediately re-executes the canonical 4-stage pipeline for the alternative product and logs `is_recommendation_accepted = 1`.

### ⚖️ 4. Cryptographically Signed Spending Mandates
Every mandate contains:
- `max_amount`: Hard cumulative spending cap.
- `allowed_category`: Whitelisted merchant category.
- `allowed_merchant_trust_level`: Minimum trust floor (1.0 to 5.0).
- `max_transactions`: Hard limit on the number of authorized calls.
- `expiry_timestamp`: Absolute cutoff time.
- `human_review_threshold`: Dollar threshold above which policy-compliant purchases escalate to `HUMAN_REVIEW` rather than automated execution.
- `version`: Monotonically increasing version counter preventing rollback attacks.
- `signature`: HMAC-SHA256 signature generated using `MANDATE_SIGNING_SECRET`. If any column in SQLite is tampered with, the signature check fails immediately and rejects the request.

### ⚡ 5. 60-Second Replay & Idempotency Protection
Prevents accidental double-charging caused by network retries or looping agents. Incoming requests are hashed using SHA-256 (`mandate_id:buyer_request`). Identical requests within 60 seconds return the cached decision receipt and existing Razorpay order without hitting external APIs.

### 📊 6. Real-Data Live Session Analytics (`GET /api/analytics/summary`)
**Zero placeholder or fake metrics.** Every metric rendered on the dashboard traces directly to SQLite `audit_logs`:
- Total Approved GMV (`SUM(intent_total) WHERE decision = 'APPROVE'`)
- Settled Revenue (`SUM(intent_total) WHERE status = 'PAID_SETTLED'`)
- AI Approval Rate (`approved / total * 100`)
- In-Mandate Recommendation Switches (`COUNT(*) WHERE is_recommendation_accepted = 1`)
- Distinct Verified Transacting Merchants (`COUNT(DISTINCT intent_merchant_id)`)

### 🚨 7. Real-Time Emergency Kill Switch (`POST /api/system/pause` & `resume`)
A global circuit-breaker for operators. If an autonomous agent enters a runaway loop or anomalous behavior is detected, toggling the kill switch (via REST API or the 1-click navbar toggle) immediately freezes all transaction execution. Incoming purchase requests are intercepted before policy evaluation or Razorpay order creation, returning an immediate blocked receipt and logging the security event to the audit trail.

---

## 📄 Real Decision Receipts

Every transaction produces an auditable receipt verifying all 6 policy checks.

### Approved & Settled Receipt Example
```json
{
  "request_id": "req_8c593649514b8a",
  "timestamp": 1788462169,
  "buyer_request": "buy 1 box of organic green tea",
  "intent": {
    "item": "Organic Green Tea (50 bags)",
    "price": 450.0,
    "quantity": 1,
    "merchant_id": "merch_nature_choice"
  },
  "product_category": "groceries",
  "merchant_trust_level": 3.5,
  "decision": "APPROVE",
  "reason": "Transaction meets all mandate requirements",
  "order_id": "order_TXfkxL1l4lxyD2",
  "payment_id": "pay_test_1788462169",
  "status": "PAID_SETTLED",
  "checks": [
    {"name": "Signature Integrity", "status": true, "detail": "HMAC SHA-256 Validated"},
    {"name": "Mandate Expiry", "status": true, "detail": "Active Time Window"},
    {"name": "Transaction Limit", "status": true, "detail": "Count within limits (1/5)"},
    {"name": "Category Restriction", "status": true, "detail": "Allowed ('groceries')"},
    {"name": "Merchant Trust Score", "status": true, "detail": "Score (3.5) >= Required (3.0)"},
    {"name": "Policy Budget Cap", "status": true, "detail": "Cost ₹450 <= Budget ₹5,000"}
  ],
  "razorpay_url": "https://rzp.io/i/mock_order_TXfkxL1l4lxyD2"
}
```

### Escalated Human Review Receipt Example
```json
{
  "request_id": "req_f4a9108c5e2190",
  "timestamp": 1788462200,
  "buyer_request": "buy 3 usb-c hubs",
  "intent": {
    "item": "USB-C Hub (6-in-1)",
    "price": 2499.0,
    "quantity": 3,
    "merchant_id": "merch_tech_hub"
  },
  "product_category": "electronics",
  "merchant_trust_level": 4.6,
  "decision": "HUMAN_REVIEW",
  "reason": "Transaction is policy-compliant but exceeds the chosen risk threshold for automated execution.",
  "order_id": "order_TXfq930LkMnv72",
  "status": "SUSPENDED",
  "checks": [
    {"name": "Signature Integrity", "status": true, "detail": "HMAC SHA-256 Validated"},
    {"name": "Mandate Expiry", "status": true, "detail": "Active Time Window"},
    {"name": "Transaction Limit", "status": true, "detail": "Count within limits (0/10)"},
    {"name": "Category Restriction", "status": true, "detail": "Allowed ('electronics')"},
    {"name": "Merchant Trust Score", "status": true, "detail": "Score (4.6) >= Required (4.0)"},
    {"name": "Policy Budget & Review", "status": true, "detail": "Cost ₹7,497 <= Budget ₹10,000; Exceeds Review Threshold ₹5,000"}
  ],
  "razorpay_url": "https://rzp.io/i/mock_order_TXfq930LkMnv72"
}
```

---

## 🛠️ Tech Stack

- **Backend Framework**: Python 3.10+ (FastAPI, Uvicorn, Pydantic)
- **Payment Gateway**: Razorpay Test-Mode Python SDK (`razorpay`) — Orders API & Payment Links
- **AI Intent Extraction**: Google Gemini API (`gemini-3.6-flash`) with local keyword fallback
- **Storage & Audit Store**: SQLite3 (Structured Mandates, Audit Trails, and Settlement State)
- **Cryptographic Security**: Python `hmac` and `hashlib` (HMAC-SHA256 tamper defense & request deduplication)
- **Dashboard UI**: Single-Page Application (HTML5, Tailwind CSS, Vanilla JS, Chart.js)

---

## 📁 Repository Structure

```
.
├── backend/
│   ├── main.py                     # FastAPI server, REST routes, pipeline orchestration
│   ├── pehrapay_client.py          # Python Agent SDK wrapper for external AI callers
│   ├── requirements.txt            # Python dependencies
│   ├── agent/
│   │   └── parser.py               # Gemini parser with automatic local keyword fallback
│   ├── mandates/
│   │   ├── models.py               # SpendingMandate data models & HMAC signer
│   │   └── store.py                # SQLite store, schema migrations, analytics queries
│   ├── policy_engine/
│   │   └── engine.py               # 6-rule deterministic policy evaluator & review tiers
│   ├── razorpay_client/
│   │   └── client.py               # Razorpay Orders & Payment Links client (Test Mode)
│   ├── static/
│   │   └── index.html              # Responsive dashboard, sandbox console & analytics
│   └── tests/                      # Automated test suite
│       ├── test_settlement_webhook.py   # Webhook settlement & idempotency tests
│       ├── test_idempotency.py          # 60-second request deduplication tests
│       ├── test_review_tier.py          # Human review threshold escalation tests
│       ├── test_kill_switch.py          # Emergency kill switch circuit breaker tests
│       ├── test_versioning.py           # Mandate versioning & cryptographic integrity tests
│       ├── test_catalog_endpoint.py     # AI catalog discovery tests
│       ├── test_goal_resolution_offline.py # Goal resolver unit tests
│       └── test_live_goal_resolution.py    # Live end-to-end Gemini test
├── data/
│   └── catalog.json                # Verified merchant catalog & trust metrics
├── .env.example                    # Environment variable configuration template
└── README.md                       # Documentation
```

---

## ⚙️ Quickstart & Local Setup

### 1. Prerequisites
- Python 3.10 or higher
- Razorpay Test Key ID & Secret ([Razorpay Dashboard](https://dashboard.razorpay.com/))
- Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/))

### 2. Installation
```bash
git clone https://github.com/vanshikasabharwal11/Pehrapay.git
cd Pehrapay
python -m venv venv

# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

pip install -r backend/requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the project root:
```env
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_key_secret
GEMINI_API_KEY=your_gemini_api_key
MANDATE_SIGNING_SECRET=your_secret_signing_key
```

> 🔑 **HMAC Key Persistence**: If `MANDATE_SIGNING_SECRET` is not set, `backend/mandates/store.py` generates a 64-character hex key and appends it to `.env` automatically, ensuring signatures remain valid across server restarts.

### 4. Run the Server
```bash
uvicorn backend.main:app --reload
```
Navigate to [**http://127.0.0.1:8000**](http://127.0.0.1:8000) in your browser.

---

## 🧪 Automated Test Suite

Run the test suite to verify pipeline behavior across all authorization branches:

```bash
# 1. Test Settlement Webhook Lifecycle & Idempotency
python -m backend.tests.test_settlement_webhook

# 2. Test 60-Second Replay / Idempotency Cache
python -m backend.tests.test_idempotency

# 3. Test Human Review Threshold Escalation
python -m backend.tests.test_review_tier

# 4. Test Emergency Kill Switch Circuit Breaker
python -m backend.tests.test_kill_switch

# 5. Test Mandate Versioning & Tamper-Evident HMAC
python -m backend.tests.test_versioning

# 6. Test Catalog Discovery Endpoint
python -m backend.tests.test_catalog_endpoint

# 7. Test Goal-Based Product Resolver (Offline)
python -m backend.tests.test_goal_resolution_offline

# 8. Test Live Gemini Pipeline (Requires GEMINI_API_KEY)
python -m backend.tests.test_live_goal_resolution
```

---

*Built for the **Razorpay AI Hackathon** — Track 01: AI Growth & Agentic Commerce.*
