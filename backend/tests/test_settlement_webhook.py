"""
Unit test for Priority 1: Simulated Settlement Loop (Webhook + Payment Capture)
Verifies:
1. Approved purchase creates order_id with status 'AUTHORIZED'.
2. Calling POST /api/webhooks/razorpay updates status in DB to 'PAID_SETTLED' and stores payment_id.
3. Duplicate webhook calls for the same order_id are idempotent (return 200, status stays 'PAID_SETTLED', budget is not double-counted).
4. Webhook with invalid order_id returns 404.
"""

import time
from fastapi.testclient import TestClient
from backend.main import app, store
from backend.mandates.models import SpendingMandate

client = TestClient(app)

def test_settlement_webhook_lifecycle():
    print("\n==================================================")
    print("   TEST: SIMULATED SETTLEMENT WEBHOOK LIFECYCLE   ")
    print("==================================================")

    now = int(time.time())
    mandate_id = f"mandate_test_settle_{now}"
    
    # 1. Create a clean test mandate
    mandate = SpendingMandate(
        purpose="Settlement Webhook Test Mandate",
        max_amount=5000.0,
        allowed_category="groceries",
        allowed_merchant_trust_level=3.0,
        max_transactions=5,
        expiry_timestamp=now + 86400 * 2
    )
    store.create_mandate(mandate_id, mandate)
    spent_initial = store.get_spent_amount(mandate_id, 1)
    assert spent_initial == 0.0, f"Expected 0 spent initially, got {spent_initial}"

    # 2. Execute an approved purchase
    purchase_payload = {
        "mandate_id": mandate_id,
        "buyer_request": "buy 1 box of organic green tea"
    }
    res = client.post("/api/purchase", json=purchase_payload)
    assert res.status_code == 200, f"Purchase failed with status {res.status_code}: {res.text}"
    purchase_data = res.json()
    assert purchase_data["decision"] == "APPROVE", f"Expected APPROVE, got {purchase_data['decision']}"
    
    order_id = purchase_data.get("order_id")
    assert order_id is not None, "Expected order_id in purchase response"
    assert purchase_data["status"] == "AUTHORIZED", f"Expected status 'AUTHORIZED', got {purchase_data['status']}"

    # Check DB record pre-settlement
    record_pre = store.get_audit_log_by_order_id(order_id)
    assert record_pre is not None, "Expected audit log record for order"
    assert record_pre["status"] == "AUTHORIZED", f"Expected DB status 'AUTHORIZED', got {record_pre['status']}"
    assert record_pre["payment_id"] is None
    
    spent_after_auth = store.get_spent_amount(mandate_id, 1)
    assert spent_after_auth == 450.0, f"Expected 450 reserved budget, got {spent_after_auth}"
    print(f"[STEP 1 PASS] Purchase approved: order_id={order_id}, status=AUTHORIZED, reserved_budget=Rs.{spent_after_auth}")

    # 3. Call Webhook to settle payment
    webhook_payload = {
        "event": "payment.captured",
        "order_id": order_id,
        "payment_id": f"pay_test_{now}",
        "status": "captured"
    }
    wh_res = client.post("/api/webhooks/razorpay", json=webhook_payload)
    assert wh_res.status_code == 200, f"Webhook failed: {wh_res.text}"
    wh_data = wh_res.json()
    assert wh_data["status"] == "success"
    assert wh_data["transaction_status"] == "PAID_SETTLED"
    assert wh_data["payment_id"] == webhook_payload["payment_id"]

    # Check DB record post-settlement
    record_post = store.get_audit_log_by_order_id(order_id)
    assert record_post["status"] == "PAID_SETTLED", f"Expected status 'PAID_SETTLED', got {record_post['status']}"
    assert record_post["payment_id"] == webhook_payload["payment_id"]
    assert record_post["settlement_timestamp"] is not None
    print(f"[STEP 2 PASS] Webhook settled: order_id={order_id}, payment_id={record_post['payment_id']}, status=PAID_SETTLED")

    # 4. Assert Budget is NOT double-counted after settlement
    spent_after_settle = store.get_spent_amount(mandate_id, 1)
    assert spent_after_settle == 450.0, f"Budget should stay 450 after settlement, got {spent_after_settle}"
    print(f"[STEP 3 PASS] Budget verified: Rs.{spent_after_settle} (no double-deduction)")

    # 5. Call Webhook again to test IDEMPOTENCY
    wh_res_duplicate = client.post("/api/webhooks/razorpay", json=webhook_payload)
    assert wh_res_duplicate.status_code == 200, "Duplicate webhook call failed"
    dup_data = wh_res_duplicate.json()
    assert dup_data["transaction_status"] == "PAID_SETTLED"
    
    # Assert budget remains unchanged
    spent_after_dup = store.get_spent_amount(mandate_id, 1)
    assert spent_after_dup == 450.0, f"Budget should stay 450 after duplicate webhook, got {spent_after_dup}"
    print(f"[STEP 4 PASS] Webhook idempotency verified: duplicate call safely ignored")

    # 6. Test Webhook with invalid order_id returns 404
    wh_res_invalid = client.post("/api/webhooks/razorpay", json={"order_id": "order_non_existent_12345"})
    assert wh_res_invalid.status_code == 404
    print(f"[STEP 5 PASS] Unknown order_id rejected with 404 Not Found")

    print("\n[SUCCESS] All Settlement Webhook lifecycle & idempotency tests passed!")

if __name__ == "__main__":
    test_settlement_webhook_lifecycle()
