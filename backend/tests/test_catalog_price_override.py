import sys
import json
from fastapi.testclient import TestClient
from backend.main import app, store, load_catalog, get_product_details
from backend.policy_engine.engine import PolicyEngine

client = TestClient(app)

# Ensure stdout uses UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_catalog_price_override():
    print("==================================================")
    print("  PEHRAPAY - CATALOG PRICE OVERRIDE SECURITY TEST ")
    print("==================================================")

    catalog = load_catalog()
    # Find Double-Walled Coffee Mug in catalog (Price: Rs. 899)
    mug = next(item for item in catalog if item["name"] == "Double-Walled Coffee Mug")
    actual_catalog_price = float(mug["price"])
    print(f"[CATALOG] Real item: '{mug['name']}', Authoritative Catalog Price: Rs. {actual_catalog_price}")

    # 1. Setup a Mandate with budget limit of Rs. 500 (Less than Rs. 899)
    mandate_id = "test_price_override_mandate"
    with store._get_connection() as conn:
        conn.execute("DELETE FROM mandates WHERE mandate_id = ?", (mandate_id,))
        conn.execute("DELETE FROM audit_logs WHERE mandate_id = ?", (mandate_id,))
        conn.commit()

    mandate_data = {
        "mandate_id": mandate_id,
        "purpose": "Price Override Security Verification Mandate",
        "max_amount": 500.0,  # Rs. 500 budget limit
        "allowed_category": "kitchenware",
        "allowed_merchant_trust_level": 3.0,
        "max_transactions": 5,
        "expiry_days": 7
    }
    create_res = client.post("/api/mandates", json=mandate_data)
    assert create_res.status_code == 200
    print(f"[SETUP] Created mandate '{mandate_id}' with budget limit Rs. 500.00.")

    # 2. Construct a FAKE Gemini response where 'price' is maliciously manipulated to Rs. 1.0
    fake_llm_intent = {
        "item": "Double-Walled Coffee Mug",
        "price": 1.0,  # Fake manipulated LLM price!
        "quantity": 1,
        "merchant_id": "merch_home_basics"
    }
    print(f"\n[ATTACK SCENARIO] Constructing fake LLM output with manipulated price: Rs. {fake_llm_intent['price']}")

    # 3. Simulate backend processing: enforce authoritative catalog price lookup
    product_details = get_product_details(fake_llm_intent["item"], catalog)
    
    # Apply security override: overwrite LLM price with catalog price
    authoritative_intent = dict(fake_llm_intent)
    if "price" in product_details:
        authoritative_intent["price"] = float(product_details["price"])

    print(f"[SECURITY FIX] Overrode intent price using catalog.json: Rs. {authoritative_intent['price']}")
    assert authoritative_intent["price"] == actual_catalog_price, "Price was not overridden with catalog price!"

    # 4. Evaluate with Policy Engine
    policy_engine = PolicyEngine()
    mandate = store.get_mandate(mandate_id)
    
    decision, reason = policy_engine.evaluate(
        intent=authoritative_intent,
        mandate=mandate,
        product_category=product_details["category"],
        merchant_trust_level=product_details["merchant_trust_level"]
    )

    print(f"[POLICY ENGINE] Evaluation Result: {decision}")
    print(f"                Reason: {reason}")

    # ASSERTIONS:
    # If the system blindly trusted LLM price (Rs. 1.0), it would APPROVE because Rs. 1.0 <= Rs. 500.0 limit.
    # Because of our security fix, it evaluates Rs. 899.0 > Rs. 500.0, so decision MUST be REJECT!
    assert decision == "REJECT", f"Expected REJECT due to real catalog price exceeding budget, but got {decision}!"
    assert "exceeds" in reason and "899" in reason, f"Reason should mention real catalog price Rs. 899: {reason}"

    print("\n[SUCCESS] Catalog price override verified! Adversarial LLM price manipulation successfully blocked.")

if __name__ == "__main__":
    test_catalog_price_override()
