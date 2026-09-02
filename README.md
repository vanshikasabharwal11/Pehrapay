# PehraPay

### **One-Line Pitch**
PehraPay — a policy and trust layer that sits between an AI shopping agent's intent and real payment execution, so an AI agent can never directly spend money outside explicit, signed limits.

---

## 📌 Problem Statement
When you delegate a shopping or procurement task to an AI agent and give it access to real money, there is currently no hard boundary to protect your funds. What stops the agent from:
- Overspending past your intended budget?
- Purchasing from untrusted or malicious merchants?
- Executing duplicate or looped transactions?
- Acting on manipulated instructions from prompt injection (e.g. instructions embedded on a product page)?

Without a separate policy enforcement layer, giving an AI agent direct API keys or credit card access is extremely risky.

---

## 💡 Core Idea
PehraPay implements a strict separation of concerns:
1. **The User** creates a signed spending **Mandate** (defining budget limits, allowed categories, minimum merchant trust level, maximum transaction count, and expiry time).
2. **The AI Agent** operates in the wild: it researches products and formulates a purchase request (an **"Intent"**).
3. **The PehraPay Vault / Policy Engine** intercepts the Intent and evaluates it deterministically against the user's Mandate.
4. **Payment Execution**: Only when the deterministic Policy Engine approves the Intent does the system make a real payment call to Razorpay.

> [!IMPORTANT]
> **The Guardrail Principle**: The LLM (AI Agent) never calls a payment-affecting function directly. It only produces a structured Intent. A separate, deterministic Policy Engine is the *sole authority* that can authorize a transaction.

> [!TIP]
> **Cryptographic Mandate Integrity**: To prevent direct database tampering (e.g., modifying the SQLite record to bump a limit from Rs. 500 to Rs. 50,000), mandates are cryptographically signed using an HMAC-SHA256 signature generated over their core fields. The policy engine re-verifies this signature before running any checks.

---

## 🏗️ Architecture Diagram

```
                 +--------------------------------+
                 |            User                |
                 +---------------+----------------+
                                 |
                     1. Creates spending mandate
                                 v
                 +---------------+----------------+
                 |       PehraPay Vault           | <---+
                 +---------------+----------------+     |
                                 |                      |
                     2. Delegated task execution        | 4. Deterministic policy check
                                 v                      |    (Approve / Reject)
                 +---------------+----------------+     |
                 |           AI Agent             |     |
                 | (Browses catalog/finds product)|     |
                 +---------------+----------------+     |
                                 |                      |
                     3. Proposes Purchase Request ------+
                        (Structured Intent)
                                 |
                                 v (If Approved)
                 +---------------+----------------+
                 |        Razorpay API            |
                 |  (Order/Payment Link created)  |
                 +--------------------------------+
```

---

## 🛠️ Tech Stack
- **Backend**: Python (FastAPI)
- **Payment Gateway**: Razorpay Test-Mode SDK (Orders API & Payment Links)
- **Natural Language Parsing**: LLM (Google Gemini API: `gemini-3.5-flash`)
- **Database**: SQLite (Mandate & Audit trail store)
- **Frontend**: HTML5, Vanilla JavaScript, Tailwind CSS (Single-Page Control Console)

---

## ⚙️ Setup & Installation

### Environment Variables
Create a `.env` file in the root directory (or `backend/` directory) with the following variables:
```env
RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
GEMINI_API_KEY=your_gemini_api_key
MANDATE_SIGNING_SECRET=your_hmac_signing_secret  # If left empty, one will be generated automatically
```

### Run Locally
1. Clone the repository and navigate to the project directory:
   ```bash
   cd "Razorpay Hackathon"
   ```
2. Set up a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
4. Run the FastAPI development server:
   ```bash
   uvicorn backend.main:app --reload
   ```
5. Open your web browser and navigate to:
   [**http://127.0.0.1:8000/**](http://127.0.0.1:8000/)

---

## 📈 Build Roadmap & Status
* **Day 1**: Core plumbing (catalog, structured intent extraction, Razorpay Orders/Payment Links creation) | **100% Complete** ✅
* **Day 2**: Mandate store + deterministic policy engine + basic audit logging | **100% Complete** ✅
* **Day 3**: Adversarial testing (normal, injection, budget, duplicate, expired) | **100% Complete** ✅
* **Day 4**: Cryptographic mandate signing & tampering detection | **100% Complete** ✅
* **Day 5**: Single-page frontend dashboard | **100% Complete** ✅
* **Day 6-10 (Next Steps)**: Frontend polish, multiple merchant support, multi-agent evaluation sandbox, final demo preparation.

---
*Created for the Razorpay AI Hackathon (Track 01: Agentic Commerce).*
