import sys
import time
from fastapi.testclient import TestClient
from backend.main import app, store

client = TestClient(app)

# Ensure UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_idempotency_protection():
    print("==================================================")
    print("   PEHRAPAY - IDEMPOTENCY PROTECTION VERIFICATION ")
    print("==================================================")

    mandate_id = "test_idempotency_mandate"
    
    # 1. Clean slate for test mandate
    with store._get_connection() as conn:
        conn.execute("DELETE FROM mandates WHERE mandate_id = ?", (mandate_id,))
        conn.execute("DELETE FROM audit_logs WHERE mandate_id = ?", (mandate_id,))
        conn.commit()

    # Create test mandate (Limit: Rs. 5000, Max Txns: 5)
    mandate_payload = {
        "mandate_id": mandate_id,
        "purpose": "Idempotency Protection Test Mandate",
        "max_amount": 5000.0,
        "allowed_category": "electronics",
        "allowed_merchant_trust_level": 3.0,
        "max_transactions": 5,
        "expiry_days": 7
    }
    create_res = client.post("/api/mandates", json=mandate_payload)
    assert create_res.status_code == 200
    print(f"[SETUP] Created test mandate '{mandate_id}' with max 5 transactions limit.")

    # 2. Fire Request 1
    buyer_request = "Buy 1 adjustable laptop stand."
    payload = {
        "buyer_request": buyer_request,
        "mandate_id": mandate_id
    }
    
    print(f"\n[REQUEST 1] Submitting: '{buyer_request}'")
    t1_start = time.time()
    res1 = client.post("/api/purchase", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()

    print(f"            Decision: {data1['decision']}")
    print(f"            Request ID: {data1['request_id'][:16]}...")
    print(f"            Idempotent Replay: {data1['idempotent_replay']}")
    print(f"            Razorpay Link: {data1['razorpay_url']}")

    assert data1["decision"] == "APPROVE", f"Expected APPROVE but got {data1['decision']}"
    assert data1["idempotent_replay"] is False, "First request must NOT be a replay!"
    assert data1["razorpay_url"] is not None, "First request must create a payment link!"

    # 3. Fire Request 2 RAPIDLY (< 0.5s later)
    print(f"\n[REQUEST 2] Submitting IDENTICAL request rapidly (< 0.5s later)...")
    res2 = client.post("/api/purchase", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()

    print(f"            Decision: {data2['decision']}")
    print(f"            Request ID: {data2['request_id'][:16]}...")
    print(f"            Idempotent Replay: {data2['idempotent_replay']}")
    print(f"            Razorpay Link: {data2['razorpay_url']}")

    # Idempotency Assertions
    assert data2["decision"] == "APPROVE"
    assert data2["idempotent_replay"] is True, "Second rapid request MUST be flagged as an idempotent replay!"
    assert data2["request_id"] == data1["request_id"], "Request IDs must match for identical bucket!"
    assert data2["razorpay_url"] == data1["razorpay_url"], "Second request must return the SAME payment link!"

    # 4. Database Verification (Confirm ONLY ONE transaction count & audit log created)
    mandate_db = store.get_mandate(mandate_id)
    audit_logs = store.get_audit_logs(mandate_id)

    print(f"\n[DATABASE CHECK]")
    print(f"Current Transactions Count in DB: {mandate_db['current_transactions']} (Expected: 1)")
    print(f"Audit Logs Count in DB: {len(audit_logs)} (Expected: 1)")

    assert mandate_db["current_transactions"] == 1, f"Database transaction count should be 1, got {mandate_db['current_transactions']}"
    assert len(audit_logs) == 1, f"Audit logs count should be 1, got {len(audit_logs)}"

    print("\n[SUCCESS] Idempotency protection verified! Duplicate rapid requests return cached result and skip Razorpay order creation.")

if __name__ == "__main__":
    test_idempotency_protection()
