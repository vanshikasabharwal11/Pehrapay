import os
import json
import hmac
import hashlib
from fastapi.testclient import TestClient
from backend.main import app, store, engine
from backend.mandates.models import SpendingMandate

client = TestClient(app)

def test_human_review_tier():
    print("==================================================")
    print("       PEHRAPAY - HUMAN REVIEW TIER TEST          ")
    print("==================================================")
    
    # 1. Setup - Create a mandate with a human_review_threshold set
    mandate_id = "test_review_tier_mandate"
    # Clean previous records if any
    with store._get_connection() as conn:
        conn.execute("DELETE FROM mandates WHERE mandate_id = ?", (mandate_id,))
        conn.execute("DELETE FROM audit_logs WHERE mandate_id = ?", (mandate_id,))
        conn.commit()

    # Create the test mandate with: limit 5000, human_review_threshold 1000
    mandate_data = {
        "mandate_id": mandate_id,
        "purpose": "Human Review Policy Mandate",
        "max_amount": 5000.0,
        "allowed_category": "electronics",
        "allowed_merchant_trust_level": 3.0,
        "max_transactions": 5,
        "expiry_days": 7,
        "human_review_threshold": 1000.0
    }
    create_res = client.post("/api/mandates", json=mandate_data)
    assert create_res.status_code == 200
    print("[SETUP] Created test mandate. Limit: Rs. 5000, Review Threshold: Rs. 1000.")

    # 2. Run transaction under review threshold (e.g. Mug or mouse for Rs. 500)
    # Note: To avoid LLM dependency, we test the policy engine directly or verify API output
    # Since we want to check both, we will verify using the API endpoint.
    purchase_data_low = {
        "buyer_request": "Buy 1 adjustable mouse for 500 rupees.",  # Mock parses to Rs. 500
        "mandate_id": mandate_id
    }
    # Note: We temporarily override the mock parser to return price=500
    # To be robust, let's call the policy engine evaluate directly with custom intent!
    mandate = store.get_mandate(mandate_id)
    assert mandate is not None
    assert mandate["human_review_threshold"] == 1000.0
    
    # Verify cryptographic signature verification holds for this mandate
    sig_ok = engine._verify_mandate_signature(mandate)
    assert sig_ok is True
    print("[STEP 1] Confirmed mandate signature verifies successfully (HMAC includes threshold).")

    # Evaluate transaction UNDER threshold (Rs. 500)
    intent_low = {"item": "Adjustable Mouse", "price": 500.0, "quantity": 1, "merchant_id": "merch_tech_essentials"}
    decision_low, reason_low = engine.evaluate(
        intent=intent_low,
        mandate=mandate,
        product_category="electronics",
        merchant_trust_level=4.5
    )
    print(f"[STEP 2] Under-threshold transaction (Rs. 500): {decision_low} (Reason: {reason_low})")
    assert decision_low == "APPROVE"

    # 3. Evaluate transaction OVER threshold (Rs. 1500)
    intent_high = {"item": "Adjustable Laptop Stand", "price": 1500.0, "quantity": 1, "merchant_id": "merch_tech_essentials"}
    decision_high, reason_high = engine.evaluate(
        intent=intent_high,
        mandate=mandate,
        product_category="electronics",
        merchant_trust_level=4.5
    )
    print(f"[STEP 3] Over-threshold transaction (Rs. 1500): {decision_high} (Reason: {reason_high})")
    assert decision_high == "HUMAN_REVIEW"
    assert "exceeds the chosen risk threshold" in reason_high

    # 4. Verify Cryptographic Mismatch detection on threshold tampering
    # Simulating DB attacker changing review threshold to Rs. 5000 to bypass review checks
    tampered_mandate = dict(mandate)
    tampered_mandate["human_review_threshold"] = 5000.0
    
    sig_tampered = engine._verify_mandate_signature(tampered_mandate)
    print(f"[STEP 4] Integrity validation on tampered threshold: {'FAILED (Security Halt)' if not sig_tampered else 'PASSED'}")
    assert sig_tampered is False, "Signature check should fail when review threshold is manipulated!"

    # 5. Call API purchase over threshold and verify response decision is HUMAN_REVIEW
    purchase_data_high = {
        "buyer_request": "Buy 1 adjustable laptop stand please.",  # Mock parses to Laptop Stand Rs. 1500
        "mandate_id": mandate_id
    }
    api_res = client.post("/api/purchase", json=purchase_data_high)
    assert api_res.status_code == 200
    api_data = api_res.json()
    print(f"[STEP 5] API endpoint result for over-threshold transaction: {api_data['decision']} (Reason: {api_data['reason']})")
    assert api_data["decision"] == "HUMAN_REVIEW"
    assert api_data["razorpay_url"] is not None # Razorpay URL generated for manual approval
    
    print("[SUCCESS] Human Review Tier and Cryptographic Validation verified successfully!")

if __name__ == "__main__":
    test_human_review_tier()
