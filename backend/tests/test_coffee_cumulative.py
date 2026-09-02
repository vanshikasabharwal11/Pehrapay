import sys
import time
from fastapi.testclient import TestClient
from backend.main import app, store, seed_database

client = TestClient(app)

# Ensure UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_coffee_cumulative():
    print("==================================================")
    print("  PEHRAPAY - CUMULATIVE BUDGET & COFFEE TEST      ")
    print("==================================================")

    # 1. Clean slate for mandate_coffee
    mandate_id = "mandate_coffee"
    with store._get_connection() as conn:
        conn.execute("DELETE FROM mandates WHERE mandate_id = ?", (mandate_id,))
        conn.execute("DELETE FROM audit_logs WHERE mandate_id = ?", (mandate_id,))
        conn.commit()

    # Re-seed mandate_coffee (budget: Rs. 2000)
    seed_database()
    
    mandate = store.get_mandate(mandate_id)
    initial_budget = mandate["max_amount"]
    spent_initial = store.get_spent_amount(mandate_id, mandate["version"])
    rem_initial = max(0.0, initial_budget - spent_initial)

    print(f"[SETUP] Initial Mandate: '{mandate_id}' (v{mandate['version']})")
    print(f"        Max Budget: Rs. {initial_budget:.2f} | Spent: Rs. {spent_initial:.2f} | Remaining: Rs. {rem_initial:.2f}")

    # =========================================================================
    # PART 1: Normal Legitimate Purchase (1 bag Coffee Beans = Rs. 1200)
    # =========================================================================
    req_1 = {
        "buyer_request": "Buy 1 bag of Premium Arabica Coffee Beans",
        "mandate_id": mandate_id
    }
    print(f"\n--- [TRANSACTION 1] Executing Request: '{req_1['buyer_request']}' ---")
    res_1 = client.post("/api/purchase", json=req_1)
    assert res_1.status_code == 200
    data_1 = res_1.json()

    print(f"Parsed Intent Item: '{data_1['intent']['item']}'")
    print(f"Enforced Price: Rs. {data_1['intent']['price']}")
    print(f"Decision: {data_1['decision']} (Reason: {data_1['reason']})")
    print(f"Razorpay Link: {data_1['razorpay_url']}")

    # Verification assertions for Txn 1
    assert data_1["decision"] == "APPROVE", f"Expected APPROVE but got {data_1['decision']}"
    assert data_1["razorpay_url"] is not None and "rzp.io" in data_1["razorpay_url"], "Expected a real Razorpay payment link!"

    spent_after_1 = store.get_spent_amount(mandate_id, mandate["version"])
    rem_after_1 = max(0.0, initial_budget - spent_after_1)
    print(f"[BUDGET STATUS] Spent so far: Rs. {spent_after_1:.2f} | REMAINING BUDGET: Rs. {rem_after_1:.2f}")
    assert rem_after_1 == 800.0, f"Remaining budget should be 800.0, got {rem_after_1}"

    # =========================================================================
    # PART 2: Second Purchase (1 bag Coffee Beans = Rs. 1200 distinct second request)
    # =========================================================================
    req_2 = {
        "buyer_request": "Order another 1 bag of Premium Arabica Coffee Beans",
        "mandate_id": mandate_id
    }
    print(f"\n--- [TRANSACTION 2] Executing Second Request: '{req_2['buyer_request']}' ---")
    res_2 = client.post("/api/purchase", json=req_2)
    assert res_2.status_code == 200
    data_2 = res_2.json()

    print(f"Parsed Intent Item: '{data_2['intent']['item']}'")
    print(f"Enforced Price: Rs. {data_2['intent']['price']}")
    print(f"Decision: {data_2['decision']}")
    print(f"Reason: {data_2['reason']}")
    print(f"Razorpay Link: {data_2['razorpay_url']}")

    # Verification assertions for Txn 2
    assert data_2["decision"] == "REJECT", f"Expected REJECT due to cumulative budget, but got {data_2['decision']}"
    assert "exceeds the remaining mandate budget of ₹800" in data_2["reason"], f"Reason missing expected budget detail: {data_2['reason']}"
    assert data_2["razorpay_url"] is None, "Razorpay link must be SKIPPED on REJECT!"

    spent_after_2 = store.get_spent_amount(mandate_id, mandate["version"])
    rem_after_2 = max(0.0, initial_budget - spent_after_2)
    print(f"[BUDGET STATUS] Spent so far: Rs. {spent_after_2:.2f} | REMAINING BUDGET: Rs. {rem_after_2:.2f}")
    assert rem_after_2 == 800.0, "Remaining budget should remain 800.0 after rejected transaction!"

    print("\n[SUCCESS] Normal purchase approval and cumulative budget enforcement verified 100%!")

if __name__ == "__main__":
    test_coffee_cumulative()
