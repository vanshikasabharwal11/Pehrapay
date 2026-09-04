import re
import os
import json
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

import hashlib
from backend.agent.parser import AgentParser, resolve_goal_based_request
from backend.razorpay_client.client import RazorpayClientWrapper
from backend.mandates.models import SpendingMandate
from backend.mandates.store import MandateStore
from backend.policy_engine.engine import PolicyEngine

app = FastAPI(title="PehraPay Vault API")

# Idempotency Cache to prevent duplicate Razorpay orders from rapid requests
idempotency_cache = {}

def get_idempotency_key(mandate_id: str, request_str: str) -> str:
    raw = f"{mandate_id}:{request_str.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def clean_idempotency_cache():
    now = time.time()
    expired = [k for k, v in idempotency_cache.items() if (now - v["timestamp"]) > 300.0]
    for k in expired:
        del idempotency_cache[k]

# Add CORS Middleware to enable communication from any client frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize systems
store = MandateStore()
engine = PolicyEngine()
parser = AgentParser()
rzp = RazorpayClientWrapper()

# Helper: Load Catalog
def load_catalog():
    current_dir = os.path.dirname(os.path.dirname(__file__))
    catalog_path = os.path.join(current_dir, "data", "catalog.json")
    with open(catalog_path, "r") as f:
        return json.load(f)

# Helper: Match product category and trust level
def get_product_details(product_name: str, catalog: list):
    catalog_lookup = {item["name"].lower(): item for item in catalog}
    item_details = catalog_lookup.get(product_name.lower())
    if not item_details:
        for name, details in catalog_lookup.items():
            if name in product_name.lower() or product_name.lower() in name:
                return details
        return {"category": "unknown", "merchant_trust_level": 0.0}
    return item_details

# Seed DB if empty
def seed_database():
    existing = store.get_mandate("mandate_coffee")
    if not existing:
        print("[SEED] Seeding sample mandates into SQLite database...")
        now = int(time.time())
        
        # 1. Coffee Mandate (groceries, budget Rs. 2000, trust 3.0)
        store.create_mandate("mandate_coffee", SpendingMandate(
            purpose="Office Coffee Procurement",
            max_amount=2000.0,
            allowed_category="groceries",
            allowed_merchant_trust_level=3.0,
            max_transactions=5,
            expiry_timestamp=now + 86400 * 7 # 7 days
        ))
        
        # 2. Mug Mandate (kitchenware, budget Rs. 500, trust 3.5)
        store.create_mandate("mandate_mug", SpendingMandate(
            purpose="Office Mug Budget",
            max_amount=500.0,
            allowed_category="kitchenware",
            allowed_merchant_trust_level=3.5,
            max_transactions=2,
            expiry_timestamp=now + 86400 * 7
        ))
        
        # 3. Lamp Mandate (electronics, budget Rs. 5000, trust 4.0)
        store.create_mandate("mandate_lamp", SpendingMandate(
            purpose="Desk Accessories Budget",
            max_amount=5000.0,
            allowed_category="electronics",
            allowed_merchant_trust_level=4.0,
            max_transactions=5,
            expiry_timestamp=now + 86400 * 7
        ))
        
        # 4. Expired Mandate (expired 1 hour ago)
        store.create_mandate("mandate_expired", SpendingMandate(
            purpose="Expired Gym Mandate",
            max_amount=5000.0,
            allowed_category="sports_fitness",
            allowed_merchant_trust_level=3.0,
            max_transactions=5,
            expiry_timestamp=now - 3600
        ))
        
        # 5. One Txn Mandate (electronics, max txn 1)
        store.create_mandate("mandate_one_txn", SpendingMandate(
            purpose="Single Transaction Limit Test",
            max_amount=5000.0,
            allowed_category="electronics",
            allowed_merchant_trust_level=3.0,
            max_transactions=1,
            expiry_timestamp=now + 86400 * 7
        ))
        
        # 6. Page 2 Example: Office Pantry Mandate (groceries, budget Rs. 5000, trust 4.0, 3 txns remaining, threshold Rs. 1000)
        store.create_mandate("mandate_pantry", SpendingMandate(
            purpose="Office Pantry",
            max_amount=5000.0,
            allowed_category="groceries",
            allowed_merchant_trust_level=4.0,
            max_transactions=5,
            expiry_timestamp=now + 64800, # 18 hours
            human_review_threshold=1000.0
        ))
        # Set 2 transactions used to leave 3 remaining
        store.increment_transaction_count("mandate_pantry")
        store.increment_transaction_count("mandate_pantry")

        # 7. Page 2 Example: Developer Tools Mandate (electronics, budget Rs. 10000, trust 4.0, threshold Rs. 5000)
        store.create_mandate("mandate_dev", SpendingMandate(
            purpose="Developer Tools",
            max_amount=10000.0,
            allowed_category="electronics",
            allowed_merchant_trust_level=4.0,
            max_transactions=10,
            expiry_timestamp=now + 86400 * 30, # 30 days
            human_review_threshold=5000.0
        ))

        # 8. Page 2 Example: Office Travel Expenses Mandate (apparel/groceries, budget Rs. 25000, trust 4.0, threshold Rs. 15000)
        store.create_mandate("mandate_travel", SpendingMandate(
            purpose="Office Travel Expenses",
            max_amount=25000.0,
            allowed_category="groceries",
            allowed_merchant_trust_level=4.0,
            max_transactions=5,
            expiry_timestamp=now + 86400 * 14, # 14 days
            human_review_threshold=15000.0
        ))
        
        print("[SEED] Seeding successful.")

# Run seeding on startup
@app.on_event("startup")
def startup_event():
    seed_database()

# Pydantic models for Requests
class PurchaseRequest(BaseModel):
    buyer_request: str
    mandate_id: str
    is_recommendation_accepted: Optional[bool] = False

class MandateCreateRequest(BaseModel):
    mandate_id: str
    purpose: str
    max_amount: float
    allowed_category: str
    allowed_merchant_trust_level: float
    max_transactions: int
    expiry_days: int
    human_review_threshold: Optional[float] = None

# Serve frontend HTML
@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    html_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Frontend HTML file not found.")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

# API Endpoints
@app.get("/api/catalog")
def get_catalog():
    try:
        return load_catalog()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/mandates")
def get_mandates():
    try:
        # SQLite returns all mandates
        with store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT mandate_id FROM mandates WHERE status = 'active'")
            ids = [row[0] for row in cursor.fetchall()]
        
        mandates = []
        for mid in ids:
            m = store.get_mandate(mid)
            if m:
                mandates.append(m)
        return mandates
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/mandates")
def create_mandate(req: MandateCreateRequest):
    try:
        now = int(time.time())
        mandate = SpendingMandate(
            purpose=req.purpose,
            max_amount=req.max_amount,
            allowed_category=req.allowed_category,
            allowed_merchant_trust_level=req.allowed_merchant_trust_level,
            max_transactions=req.max_transactions,
            expiry_timestamp=now + (req.expiry_days * 86400),
            human_review_threshold=req.human_review_threshold
        )
        store.create_mandate(req.mandate_id, mandate)
        return {"status": "success", "mandate": store.get_mandate(req.mandate_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audit-logs")
def get_audit_logs():
    try:
        return store.get_audit_logs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/purchase")
def execute_purchase(req: PurchaseRequest):
    now_ts = time.time()
    clean_idempotency_cache()

    # Generate request_id for idempotency check (60s window)
    request_id = get_idempotency_key(req.mandate_id, req.buyer_request)

    # Check if identical request was processed in last 60 seconds
    if request_id in idempotency_cache:
        entry = idempotency_cache[request_id]
        if (now_ts - entry["timestamp"]) <= 60.0:
            print(f"[IDEMPOTENCY] Replayed duplicate request '{req.buyer_request}' within 60s window (request_id: {request_id[:12]}...). Returning cached result.")
            cached_resp = dict(entry["response"])
            cached_resp["idempotent_replay"] = True
            return cached_resp

    # Check if system is emergency paused
    if store.is_agent_paused():
        decision = "REJECT"
        reason = "System Paused - Emergency Kill Switch Active"
        dummy_intent = {"item": "N/A", "price": 0.0, "quantity": 0, "merchant_id": "N/A"}
        try:
            store.log_audit(
                timestamp=int(time.time()),
                mandate_id=req.mandate_id,
                buyer_request=req.buyer_request,
                intent=dummy_intent,
                decision=decision,
                reason=reason,
                mandate_version=1
            )
        except Exception as e:
            print(f"Warning: Failed to log audit: {e}")
            
        return {
            "intent": dummy_intent,
            "product_category": "unknown",
            "merchant_trust_level": 0.0,
            "decision": decision,
            "reason": reason,
            "razorpay_url": None,
            "fallback_active": False,
            "request_id": request_id,
            "idempotent_replay": False
        }

    # Retrieve mandate
    mandate = store.get_mandate(req.mandate_id)
    if not mandate:
        raise HTTPException(status_code=404, detail=f"Mandate '{req.mandate_id}' not found.")

    catalog = load_catalog()
    
    # 1. Parse natural language request to structured intent
    try:
        intent = parser.parse_buyer_request(req.buyer_request, catalog)
        fallback_active = parser.last_call_fallback
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse request: {e}")

    # 2. Match catalog properties & Goal-Based Product Selection
    existing_goal_notes = intent.get("goal_resolution_notes")
    resolved_product, goal_notes_or_error = resolve_goal_based_request(req.buyer_request, intent, catalog)
    goal_notes_or_error = goal_notes_or_error or existing_goal_notes

    if not resolved_product:
        # Step 7: No catalog products match criteria -> REJECT
        decision = "REJECT"
        reason = goal_notes_or_error or "No catalog products found matching your request criteria"
        try:
            store.log_audit(
                timestamp=int(time.time()),
                mandate_id=req.mandate_id,
                buyer_request=req.buyer_request,
                intent=intent,
                decision=decision,
                reason=reason,
                mandate_version=mandate["version"]
            )
        except Exception as e:
            print(f"Warning: Failed to log audit: {e}")

        response_payload = {
            "intent": intent,
            "product_category": "unknown",
            "merchant_trust_level": 0.0,
            "decision": decision,
            "reason": reason,
            "razorpay_url": None,
            "fallback_active": fallback_active,
            "razorpay_fallback_active": rzp.fallback_active,
            "request_id": request_id,
            "idempotent_replay": False,
            "goal_resolution_notes": None
        }
        idempotency_cache[request_id] = {"timestamp": now_ts, "response": response_payload}
        return response_payload

    product_details = resolved_product
    category = product_details.get("category", "unknown")
    trust_level = float(product_details.get("merchant_trust_level", 0.0))

    # Overwrite intent with authoritative catalog details
    intent["item"] = product_details["name"]
    if "price" in product_details:
        intent["price"] = float(product_details["price"])
    if "merchant_id" in product_details:
        intent["merchant_id"] = product_details["merchant_id"]

    # 3. Evaluate Policy Engine
    try:
        decision, reason = engine.evaluate(
            intent=intent,
            mandate=mandate,
            product_category=category,
            merchant_trust_level=trust_level,
            store=store
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Policy evaluation error: {e}")

    # 4. Conditional payment execution & order generation
    order_id = None
    razorpay_url = None
    trans_status = "BLOCKED"

    if decision == "APPROVE":
        trans_status = "AUTHORIZED"
        try:
            total_price = intent["price"] * intent["quantity"]
            description = f"Purchase: {intent['quantity']}x {intent['item']}"
            
            # Create order and link
            order_res = rzp.create_order(amount_in_rupees=total_price)
            order_id = order_res["order_id"]
            razorpay_url = rzp.generate_payment_link(
                order_id=order_id,
                amount_in_rupees=total_price,
                description=description
            )
            # Increment transaction count
            store.increment_transaction_count(req.mandate_id, version=mandate["version"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Razorpay execution failed: {e}")
    elif decision == "HUMAN_REVIEW":
        trans_status = "SUSPENDED"
        try:
            total_price = intent["price"] * intent["quantity"]
            description = f"Purchase: {intent['quantity']}x {intent['item']} (Human Approved)"
            order_res = rzp.create_order(amount_in_rupees=total_price)
            order_id = order_res["order_id"]
            razorpay_url = rzp.generate_payment_link(
                order_id=order_id,
                amount_in_rupees=total_price,
                description=description
            )
        except Exception as e:
            print(f"Warning: Failed to create order for human review: {e}")

    # 5. Log to Audit with real order_id, status, and recommendation acceptance flag
    try:
        store.log_audit(
            timestamp=int(time.time()),
            mandate_id=req.mandate_id,
            buyer_request=req.buyer_request,
            intent=intent,
            decision=decision,
            reason=reason,
            mandate_version=mandate["version"],
            order_id=order_id,
            status=trans_status,
            is_recommendation_accepted=bool(req.is_recommendation_accepted)
        )
    except Exception as e:
        print(f"Warning: Failed to log audit: {e}")

    # C3 — Intelligent Cross-Sell Recommendation (within mandate constraints)
    recommendation = None
    if decision == "APPROVE":
        try:
            remaining_budget = mandate["max_amount"] - store.get_spent_amount(req.mandate_id)
            candidates = [
                p for p in catalog
                if p["name"] != product_details["name"]
                and p.get("category", "").lower() == category
                and float(p.get("price", 0)) <= remaining_budget
                and float(p.get("merchant_trust_level", 0)) >= mandate.get("allowed_merchant_trust_level", 0)
            ]
            if candidates:
                candidates.sort(key=lambda x: x["merchant_trust_level"], reverse=True)
                rec = candidates[0]
                recommendation = {
                    "item": rec["name"],
                    "price": rec["price"],
                    "merchant_trust_level": rec["merchant_trust_level"],
                    "reason": f"Also in {category} · ₹{rec['price']:g} · trust {rec['merchant_trust_level']}/5 · within your remaining mandate budget"
                }
        except Exception as e:
            print(f"Warning: Recommendation generation failed: {e}")

    # Return response payload
    response_payload = {
        "intent": intent,
        "product_category": category,
        "merchant_trust_level": trust_level,
        "decision": decision,
        "reason": reason,
        "order_id": order_id,
        "status": trans_status,
        "razorpay_url": razorpay_url,
        "fallback_active": fallback_active,
        "razorpay_fallback_active": rzp.fallback_active,
        "request_id": request_id,
        "idempotent_replay": False,
        "goal_resolution_notes": goal_notes_or_error,
        "recommendation": recommendation
    }

    # Cache response for idempotency protection
    idempotency_cache[request_id] = {
        "timestamp": now_ts,
        "response": response_payload
    }

    return response_payload

@app.post("/api/webhooks/razorpay")
def razorpay_webhook(data: dict):
    """
    Receives and processes simulated or real Razorpay webhook events (order.paid / payment.captured).
    Verifies that order_id exists in the transaction store, transitions status from 
    AUTHORIZED to PAID_SETTLED, records payment_id and settlement timestamp, and is idempotent.
    """
    # 1. Parse order_id and payment_id from standard Razorpay payload or flat simulation payload
    order_id = data.get("order_id")
    payment_id = data.get("payment_id")
    status = data.get("status", "paid")
    event = data.get("event", "order.paid")

    if not order_id and "payload" in data:
        p = data.get("payload", {})
        if "payment" in p and "entity" in p["payment"]:
            order_id = p["payment"]["entity"].get("order_id")
            payment_id = payment_id or p["payment"]["entity"].get("id")
        elif "order" in p and "entity" in p["order"]:
            order_id = p["order"]["entity"].get("id")

    if not order_id:
        raise HTTPException(status_code=400, detail="Missing order_id in webhook payload.")

    # Generate payment_id if not provided
    if not payment_id:
        payment_id = f"pay_{hashlib.sha256(f'{order_id}:{time.time()}'.encode()).hexdigest()[:14]}"

    # 2. Verify order_id exists in audit_logs
    record = store.get_audit_log_by_order_id(order_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found in audit store.")

    # 3. Idempotent settlement update (does not double-deduct or corrupt budget)
    settlement_ts = int(time.time())
    updated_record = store.update_transaction_settlement(
        order_id=order_id,
        payment_id=payment_id,
        settlement_timestamp=settlement_ts
    )

    return {
        "status": "success",
        "event": event,
        "order_id": order_id,
        "payment_id": updated_record["payment_id"],
        "transaction_status": updated_record["status"],
        "settled_at": updated_record["settlement_timestamp"],
        "mandate_id": updated_record["mandate_id"],
        "amount": updated_record["intent_total"]
    }

@app.get("/api/analytics/summary")
def get_analytics_summary():
    """
    Returns real live-session analytics calculated strictly from the SQLite audit_logs table.
    """
    try:
        return store.get_analytics_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/status")
def get_system_status():
    try:
        return {"paused": store.is_agent_paused()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system/pause")
def pause_system():
    try:
        store.set_agent_paused(True)
        return {"paused": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system/resume")
def resume_system():
    try:
        store.set_agent_paused(False)
        return {"paused": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
