import os
import json
import time
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from backend.agent.parser import AgentParser
from backend.razorpay_client.client import RazorpayClientWrapper
from backend.mandates.models import SpendingMandate
from backend.mandates.store import MandateStore
from backend.policy_engine.engine import PolicyEngine

def load_catalog():
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    catalog_path = os.path.join(current_dir, "data", "catalog.json")
    with open(catalog_path, "r") as f:
        return json.load(f)

def run_versioning_tests():
    print("==================================================")
    print("       PEHRAPAY - POLICY VERSIONING TESTS         ")
    print("==================================================")

    store = MandateStore()
    engine = PolicyEngine()
    parser = AgentParser()
    catalog = load_catalog()

    # Clean existing mandates/logs for test isolation
    with store._get_connection() as conn:
        conn.execute("DELETE FROM mandates WHERE mandate_id = 'test_versioning'")
        conn.execute("DELETE FROM audit_logs WHERE mandate_id = 'test_versioning'")
        conn.commit()

    now = int(time.time())
    mandate_id = "test_versioning"

    # Helper: Product categories & trust levels lookup
    catalog_lookup = {item["name"].lower(): item for item in catalog}
    def get_product_details(product_name: str):
        item_details = catalog_lookup.get(product_name.lower())
        if not item_details:
            for name, details in catalog_lookup.items():
                if name in product_name.lower() or product_name.lower() in name:
                    return details
            return {"category": "unknown", "merchant_trust_level": 0.0}
        return item_details

    # =========================================================================
    # STEP 1: Create Mandate v1 (Limit Rs. 2000)
    # =========================================================================
    print("\n--- [STEP 1] Creating Mandate Version 1 (Limit: Rs. 2000) ---")
    mandate_v1_input = SpendingMandate(
        purpose="Versioning Test - Initial",
        max_amount=2000.0,
        allowed_category="electronics",
        allowed_merchant_trust_level=3.0,
        max_transactions=5,
        expiry_timestamp=now + 3600
    )
    
    m_v1 = store.create_mandate(mandate_id, mandate_v1_input)
    print(f"Mandate created: version={m_v1['version']}, status={m_v1['status']}, limit=Rs. {m_v1['max_amount']:.2f}")
    assert m_v1["version"] == 1, f"Expected version 1, got {m_v1['version']}"
    assert m_v1["status"] == "active", f"Expected active status, got {m_v1['status']}"

    # =========================================================================
    # STEP 2: Run Purchase (Rs. 1500) -> Should APPROVE under v1
    # =========================================================================
    buyer_request = "Buy 1 adjustable laptop stand please."  # Rs. 1500, electronics, trusted
    print(f"\n--- [STEP 2] Request (under v1): \"{buyer_request}\" ---")
    
    intent_v1 = parser.parse_buyer_request(buyer_request, catalog)
    prod_meta = get_product_details(intent_v1["item"])
    
    # Retrieve active version (should be v1)
    active_mandate = store.get_mandate(mandate_id)
    print(f"Retrieved active mandate: version={active_mandate['version']}, limit=Rs. {active_mandate['max_amount']:.2f}")
    
    decision_v1, reason_v1 = engine.evaluate(
        intent=intent_v1,
        mandate=active_mandate,
        product_category=prod_meta["category"],
        merchant_trust_level=prod_meta["merchant_trust_level"]
    )
    print(f"Decision: {decision_v1} (Reason: {reason_v1})")
    assert decision_v1 == "APPROVE", f"Expected APPROVE, got {decision_v1}"

    # Log to audit trail
    store.log_audit(
        timestamp=int(time.time()),
        mandate_id=mandate_id,
        buyer_request=buyer_request,
        intent=intent_v1,
        decision=decision_v1,
        reason=reason_v1,
        mandate_version=active_mandate["version"]
    )
    print("Logged transaction 1 to audit trail.")

    # =========================================================================
    # STEP 3: Update Mandate to v2 (Limit Rs. 500) -> v1 superseded
    # =========================================================================
    print("\n--- [STEP 3] Updating Mandate to Version 2 (Limit: Rs. 500) ---")
    mandate_v2_input = SpendingMandate(
        purpose="Versioning Test - Strict Limit",
        max_amount=500.0,  # Lower limit
        allowed_category="electronics",
        allowed_merchant_trust_level=3.0,
        max_transactions=5,
        expiry_timestamp=now + 3600
    )
    
    m_v2 = store.create_mandate(mandate_id, mandate_v2_input)
    print(f"Mandate updated: version={m_v2['version']}, status={m_v2['status']}, limit=Rs. {m_v2['max_amount']:.2f}")
    assert m_v2["version"] == 2, f"Expected version 2, got {m_v2['version']}"
    assert m_v2["status"] == "active", f"Expected active status, got {m_v2['status']}"

    # Confirm version 1 is now superseded in DB
    m_v1_after = store.get_mandate(mandate_id, version=1)
    print(f"Verified version 1 in DB: version={m_v1_after['version']}, status={m_v1_after['status']}")
    assert m_v1_after["status"] == "superseded", f"Expected superseded status, got {m_v1_after['status']}"

    # =========================================================================
    # STEP 4: Run Same Purchase (Rs. 1500) -> Should REJECT under v2
    # =========================================================================
    print(f"\n--- [STEP 4] Request (under v2): \"{buyer_request}\" ---")
    
    # Wait to avoid Gemini rate limits
    time.sleep(5)
    intent_v2 = parser.parse_buyer_request(buyer_request, catalog)
    
    # Retrieve active version (should be v2 now)
    active_mandate_v2 = store.get_mandate(mandate_id)
    print(f"Retrieved active mandate: version={active_mandate_v2['version']}, limit=Rs. {active_mandate_v2['max_amount']:.2f}")
    
    decision_v2, reason_v2 = engine.evaluate(
        intent=intent_v2,
        mandate=active_mandate_v2,
        product_category=prod_meta["category"],
        merchant_trust_level=prod_meta["merchant_trust_level"]
    )
    print(f"Decision: {decision_v2} (Reason: {reason_v2})")
    assert decision_v2 == "REJECT", f"Expected REJECT, got {decision_v2}"
    assert "exceeds the remaining mandate budget" in reason_v2, f"Expected budget reject reason, got: {reason_v2}"

    # Log to audit trail
    store.log_audit(
        timestamp=int(time.time()),
        mandate_id=mandate_id,
        buyer_request=buyer_request,
        intent=intent_v2,
        decision=decision_v2,
        reason=reason_v2,
        mandate_version=active_mandate_v2["version"]
    )
    print("Logged transaction 2 to audit trail.")

    # =========================================================================
    # STEP 5: Verify Audit Log Version Integrity
    # =========================================================================
    print("\n--- [STEP 5] Verifying Version Numbers in Audit Logs ---")
    logs = store.get_audit_logs(mandate_id)
    # logs are sorted descending by timestamp, so log[0] is txn 2 (v2), log[1] is txn 1 (v1)
    print(f"Retrieved {len(logs)} audit logs.")
    assert len(logs) == 2, f"Expected 2 audit logs, got {len(logs)}"
    
    print(f"Latest Log (Txn 2)  - Decision: {logs[0]['decision']}, Mandate Version used: {logs[0]['mandate_version']}")
    print(f"Earlier Log (Txn 1) - Decision: {logs[1]['decision']}, Mandate Version used: {logs[1]['mandate_version']}")
    
    assert logs[0]["mandate_version"] == 2, f"Expected log[0] version 2, got {logs[0]['mandate_version']}"
    assert logs[0]["decision"] == "REJECT", f"Expected log[0] REJECT, got {logs[0]['decision']}"
    
    assert logs[1]["mandate_version"] == 1, f"Expected log[1] version 1, got {logs[1]['mandate_version']}"
    assert logs[1]["decision"] == "APPROVE", f"Expected log[1] APPROVE, got {logs[1]['decision']}"

    print("\n[SUCCESS] POLICY VERSIONING UNIT TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_versioning_tests()
