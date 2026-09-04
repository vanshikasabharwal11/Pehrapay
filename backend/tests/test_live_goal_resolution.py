import sys
import json
import time
from fastapi.testclient import TestClient
from backend.main import app, store

client = TestClient(app)

# Ensure UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_live_goal_resolution_pipeline():
    print("==================================================")
    print("   PEHRAPAY - LIVE REAL GEMINI GOAL RESOLUTION    ")
    print("==================================================")

    mandate_id = "mandate_coffee"
    mandate = store.get_mandate(mandate_id)
    if not mandate:
        from backend.main import seed_database
        seed_database()
        mandate = store.get_mandate(mandate_id)
    assert mandate is not None, f"Mandate '{mandate_id}' not found in database!"

    print(f"[SETUP] Mandate: '{mandate['purpose']}' ({mandate_id} v{mandate['version']})")
    print(f"        Max Amount: Rs. {mandate['max_amount']} | Allowed Category: {mandate['allowed_category']} | Min Trust: {mandate['allowed_merchant_trust_level']}")

    # CASE 1: Request where Gemini parses exact item name
    buyer_request = "buy me coffee under ₹1000"
    payload = {"buyer_request": buyer_request, "mandate_id": mandate_id}
    print(f"\n[CASE 1 REQUEST] Submitting: '{buyer_request}'")
    res1 = client.post("/api/purchase", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()

    print("\n--- 1. GEMINI PARSED INTENT ---")
    print(json.dumps(data1["intent"], indent=2))
    print(f"Fallback Active: {data1['fallback_active']} (False = Real Gemini Output)")

    print("\n--- 2. GOAL-BASED RESOLUTION PATH ---")
    if data1.get("goal_resolution_notes"):
        print("Path Triggered: GOAL-BASED RESOLVER")
        print(f"Resolution Rationale:\n  {data1['goal_resolution_notes']}")
    else:
        print("Path Triggered: EXACT MATCH")

    print("\n--- 3. SELECTED PRODUCT & CATALOG OVERRIDE ---")
    print(f"Selected Item: '{data1['intent']['item']}'")
    print(f"Enforced Catalog Price: Rs. {data1['intent']['price']}")
    print(f"Product Category: {data1['product_category']}")

    print("\n--- 4. POLICY ENGINE FINAL DECISION ---")
    print(f"Decision: {data1['decision']}")
    print(f"Reason: {data1['reason']}")

    # CASE 2: Request triggering Goal-Based Resolver path (generic term "coffee beans under 1000")
    buyer_request2 = "purchase groceries coffee under 1000"
    payload2 = {"buyer_request": buyer_request2, "mandate_id": mandate_id}
    print(f"\n\n==================================================")
    print(f"[CASE 2 REQUEST] Submitting: '{buyer_request2}'")
    res2 = client.post("/api/purchase", json=payload2)
    assert res2.status_code == 200
    data2 = res2.json()

    print("\n--- 1. GEMINI PARSED INTENT ---")
    print(json.dumps(data2["intent"], indent=2))
    print(f"Fallback Active: {data2['fallback_active']}")

    print("\n--- 2. GOAL-BASED RESOLUTION PATH ---")
    if data2.get("goal_resolution_notes"):
        print("Path Triggered: GOAL-BASED RESOLVER")
        print(f"Resolution Rationale:\n  {data2['goal_resolution_notes']}")
    else:
        print("Path Triggered: EXACT MATCH")

    print("\n--- 3. SELECTED PRODUCT & CATALOG OVERRIDE ---")
    print(f"Selected Item: '{data2['intent']['item']}'")
    print(f"Enforced Catalog Price: Rs. {data2['intent']['price']}")
    print(f"Product Category: {data2['product_category']}")

    print("\n--- 4. POLICY ENGINE FINAL DECISION ---")
    print(f"Decision: {data2['decision']}")
    print(f"Reason: {data2['reason']}")
    # CASE 3: Request triggering Goal-Based Resolver path (generic item name "organic fairtrade coffee" not in catalog)
    buyer_request3 = "buy 1 bag of organic fairtrade coffee under 1000"
    payload3 = {"buyer_request": buyer_request3, "mandate_id": mandate_id}
    print(f"\n\n==================================================")
    print(f"[CASE 3 REQUEST] Submitting: '{buyer_request3}'")
    res3 = client.post("/api/purchase", json=payload3)
    assert res3.status_code == 200
    data3 = res3.json()

    print("\n--- 1. GEMINI PARSED INTENT ---")
    print(json.dumps(data3["intent"], indent=2))
    print(f"Fallback Active: {data3['fallback_active']}")

    print("\n--- 2. GOAL-BASED RESOLUTION PATH ---")
    if data3.get("goal_resolution_notes"):
        print("Path Triggered: GOAL-BASED RESOLVER")
        print(f"Resolution Rationale:\n  {data3['goal_resolution_notes']}")
    else:
        print("Path Triggered: EXACT MATCH")

    print("\n--- 3. SELECTED PRODUCT & CATALOG OVERRIDE ---")
    print(f"Selected Item: '{data3['intent']['item']}'")
    print(f"Enforced Catalog Price: Rs. {data3['intent']['price']}")
    print(f"Product Category: {data3['product_category']}")

    print("\n--- 4. POLICY ENGINE FINAL DECISION ---")
    print(f"Decision: {data3['decision']}")
    print(f"Reason: {data3['reason']}")
    # CASE 4: Prompt with generic term "herbal beverage under 1000" (Triggers GOAL RESOLVER path live!)
    buyer_request4 = "buy 1 box of organic herbal beverages under 1000"
    payload4 = {"buyer_request": buyer_request4, "mandate_id": mandate_id}
    print(f"\n\n==================================================")
    print(f"[CASE 4 REQUEST] Submitting: '{buyer_request4}'")
    res4 = client.post("/api/purchase", json=payload4)
    assert res4.status_code == 200
    data4 = res4.json()

    print("\n--- 1. GEMINI PARSED INTENT ---")
    print(json.dumps(data4["intent"], indent=2))
    print(f"Fallback Active: {data4['fallback_active']}")

    print("\n--- 2. GOAL-BASED RESOLUTION PATH ---")
    if data4.get("goal_resolution_notes"):
        print("Path Triggered: GOAL-BASED RESOLVER")
        print(f"Resolution Rationale:\n  {data4['goal_resolution_notes']}")
    else:
        print("Path Triggered: EXACT MATCH")

    print("\n--- 3. SELECTED PRODUCT & CATALOG OVERRIDE ---")
    print(f"Selected Item: '{data4['intent']['item']}'")
    print(f"Enforced Catalog Price: Rs. {data4['intent']['price']}")
    print(f"Product Category: {data4['product_category']}")

    print("\n--- 4. POLICY ENGINE FINAL DECISION ---")
    print(f"Decision: {data4['decision']}")
    print(f"Reason: {data4['reason']}")
    # CASE 5: Request where intent item name has NO exact match in catalog.json (Triggers GOAL RESOLVER path live!)
    buyer_request5 = "find any groceries drink option under 1000"
    payload5 = {"buyer_request": buyer_request5, "mandate_id": mandate_id}
    print(f"\n\n==================================================")
    print(f"[CASE 5 REQUEST] Submitting: '{buyer_request5}'")
    res5 = client.post("/api/purchase", json=payload5)
    assert res5.status_code == 200
    data5 = res5.json()

    print("\n--- 1. GEMINI PARSED INTENT ---")
    print(json.dumps(data5["intent"], indent=2))
    print(f"Fallback Active: {data5['fallback_active']}")

    print("\n--- 2. GOAL-BASED RESOLUTION PATH ---")
    if data5.get("goal_resolution_notes"):
        print("Path Triggered: GOAL-BASED RESOLVER")
        print(f"Resolution Rationale:\n  {data5['goal_resolution_notes']}")
    else:
        print("Path Triggered: EXACT MATCH")

    print("\n--- 3. SELECTED PRODUCT & CATALOG OVERRIDE ---")
    print(f"Selected Item: '{data5['intent']['item']}'")
    print(f"Enforced Catalog Price: Rs. {data5['intent']['price']}")
    print(f"Product Category: {data5['product_category']}")

    print("\n--- 4. POLICY ENGINE FINAL DECISION ---")
    print(f"Decision: {data5['decision']}")
    print(f"Reason: {data5['reason']}")
    print(f"Razorpay Link: {data5['razorpay_url']}")

    print("\n[SUCCESS] Live real Gemini pipeline test completed for all paths!")

if __name__ == "__main__":
    test_live_goal_resolution_pipeline()
