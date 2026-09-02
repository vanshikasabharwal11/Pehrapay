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

def run_day2_tests():
    print("==================================================")
    print("            PEHRAPAY - DAY 2 TEST RUN             ")
    print("==================================================\n")

    # 1. Load catalog & setup lookup helper
    catalog = load_catalog()
    catalog_lookup = {item["name"].lower(): item for item in catalog}

    def get_product_details(product_name: str):
        # Match product name closely in case of case mismatches
        item_details = catalog_lookup.get(product_name.lower())
        if not item_details:
            # Fallback search if exact match fails
            for name, details in catalog_lookup.items():
                if name in product_name.lower() or product_name.lower() in name:
                    return details
            # Default fallback if absolutely not found
            return {"category": "unknown", "merchant_trust_level": 0.0}
        return item_details

    # 2. Initialize Stores & Engines
    store = MandateStore()
    engine = PolicyEngine()
    parser = AgentParser()
    rzp = RazorpayClientWrapper()

    # 3. Setup Mandates
    print("[1] Initializing Spending Mandates in Database...")
    now = int(time.time())

    # Case 1 Mandate: Clean
    mandate_clean = SpendingMandate(
        purpose="Office Coffee Procurement",
        max_amount=2000.0,
        allowed_category="groceries",
        allowed_merchant_trust_level=3.0,
        max_transactions=5,
        expiry_timestamp=now + 3600 # 1 hour in future
    )
    store.create_mandate("mandate_clean", mandate_clean)

    # Case 2 Mandate: Too low budget
    mandate_low_budget = SpendingMandate(
        purpose="Office Mug Budget",
        max_amount=500.0, # Will fail (mug is Rs. 899)
        allowed_category="kitchenware",
        allowed_merchant_trust_level=3.5,
        max_transactions=2,
        expiry_timestamp=now + 3600
    )
    store.create_mandate("mandate_low_budget", mandate_low_budget)

    # Case 3 Mandate: Require high trust
    mandate_high_trust = SpendingMandate(
        purpose="Desk Accessories Budget",
        max_amount=5000.0,
        allowed_category="electronics",
        allowed_merchant_trust_level=4.0, # Will fail (lamp is 2.8)
        max_transactions=5,
        expiry_timestamp=now + 3600
    )
    store.create_mandate("mandate_high_trust", mandate_high_trust)

    # Case 4 Mandate: Expired
    mandate_expired = SpendingMandate(
        purpose="Gym Equipment Budget",
        max_amount=5000.0,
        allowed_category="sports_fitness",
        allowed_merchant_trust_level=3.0,
        max_transactions=5,
        expiry_timestamp=now - 3600 # Expired 1 hour ago
    )
    store.create_mandate("mandate_expired", mandate_expired)

    # Case 5 Mandate: Category Mismatch
    mandate_category_mismatch = SpendingMandate(
        purpose="Category Mismatch Test",
        max_amount=2000.0,
        allowed_category="groceries",
        allowed_merchant_trust_level=3.0,
        max_transactions=5,
        expiry_timestamp=now + 3600
    )
    store.create_mandate("mandate_category_mismatch", mandate_category_mismatch)

    # Case 6 Mandate: Max 1 transaction
    mandate_one_txn = SpendingMandate(
        purpose="Single Transaction Limit Test",
        max_amount=5000.0,
        allowed_category="electronics",
        allowed_merchant_trust_level=3.0,
        max_transactions=1,
        expiry_timestamp=now + 3600
    )
    store.create_mandate("mandate_one_txn", mandate_one_txn)
    print("    Mandates initialized successfully.\n")

    # 4. Define Test Cases
    test_cases = [
        {
            "id": 1,
            "name": "Case 1: Clean Case (Should APPROVE & Execute Payment)",
            "buyer_request": "I want to buy 1 bag of Premium Arabica Coffee Beans please.",
            "mandate_id": "mandate_clean"
        },
        {
            "id": 2,
            "name": "Case 2: Exceeds Max Amount Limit (Should REJECT)",
            "buyer_request": "Buy 1 double-walled coffee mug.",
            "mandate_id": "mandate_low_budget"
        },
        {
            "id": 3,
            "name": "Case 3: Merchant below Trust Threshold (Should REJECT)",
            "buyer_request": "Buy 1 smart LED desk lamp.",
            "mandate_id": "mandate_high_trust"
        },
        {
            "id": 4,
            "name": "Case 4: Expired Mandate (Should REJECT)",
            "buyer_request": "Buy 1 stainless steel water bottle.",
            "mandate_id": "mandate_expired"
        },
        {
            "id": 5,
            "name": "Case 5: Category Mismatch (Should REJECT)",
            "buyer_request": "Buy 1 adjustable laptop stand.",
            "mandate_id": "mandate_category_mismatch"
        },
        {
            "id": 6,
            "name": "Case 6a: Single Transaction Limit - First Txn (Should APPROVE & Execute Payment)",
            "buyer_request": "Buy 1 adjustable laptop stand.",
            "mandate_id": "mandate_one_txn"
        },
        {
            "id": 7,
            "name": "Case 6b: Single Transaction Limit - Second Txn (Should REJECT)",
            "buyer_request": "Buy 1 USB-C Hub (6-in-1).",
            "mandate_id": "mandate_one_txn"
        }
    ]

    # 5. Run cases
    for case in test_cases:
        print("--------------------------------------------------")
        print(f"RUNNING: {case['name']}")
        print(f"Buyer Request: \"{case['buyer_request']}\"")
        print(f"Mandate ID: {case['mandate_id']}")
        
        # A. Fetch mandate from DB
        mandate_db = store.get_mandate(case["mandate_id"])
        if not mandate_db:
            print(f"    ERROR: Mandate '{case['mandate_id']}' not found in database.")
            continue
            
        print(f"    Current Mandate state: Transactions {mandate_db['current_transactions']}/{mandate_db['max_transactions']}, Limit Rs. {mandate_db['max_amount']:.2f}")

        # B. Parse with LLM (Gemini)
        print("    Running Gemini intent parser...")
        intent = parser.parse_buyer_request(case["buyer_request"], catalog)
        print(f"    Extracted Intent: {json.dumps(intent)}")

        # C. Lookup Product properties
        product_details = get_product_details(intent["item"])
        category = product_details["category"]
        trust_level = product_details["merchant_trust_level"]
        print(f"    Matched Product: '{intent['item']}' | Category: '{category}' | Merchant Trust: {trust_level}")

        # D. Evaluate Policy Engine
        decision, reason = engine.evaluate(
            intent=intent,
            mandate=mandate_db,
            product_category=category,
            merchant_trust_level=trust_level,
            current_time=int(time.time())
        )
        print(f"    POLICY ENGINE DECISION: {decision}")
        print(f"    Reason: {reason}")

        # E. Audit Log
        store.log_audit(
            timestamp=int(time.time()),
            mandate_id=case["mandate_id"],
            buyer_request=case["buyer_request"],
            intent=intent,
            decision=decision,
            reason=reason
        )

        # F. Wire to Razorpay & Store updates
        razorpay_status = "SKIPPED (Rejected by policy)"
        if decision == "APPROVE":
            total_price = intent["price"] * intent["quantity"]
            description = f"Purchase: {intent['quantity']}x {intent['item']}"
            
            print(f"    Executing Razorpay payment setup for Rs. {total_price:.2f}...")
            try:
                order_res = rzp.create_order(amount_in_rupees=total_price)
                payment_link = rzp.generate_payment_link(
                    order_id=order_res["order_id"],
                    amount_in_rupees=total_price,
                    description=description
                )
                razorpay_status = f"SUCCESS (Order: {order_res['order_id']}, Link: {payment_link})"
                
                # Increment mandate's transaction count in database
                store.increment_transaction_count(case["mandate_id"])
                updated_mandate = store.get_mandate(case["mandate_id"])
                print(f"    Mandate transaction count incremented to: {updated_mandate['current_transactions']}/{updated_mandate['max_transactions']}")
                
            except Exception as e:
                razorpay_status = f"FAILED ({e})"
                print(f"    ERROR executing Razorpay: {e}")

        print(f"    Razorpay Call Status: {razorpay_status}\n")

    # 6. Display Audit Logs
    print("==================================================")
    print("           SQLITE AUDIT LOG VERIFICATION          ")
    print("==================================================")
    logs = store.get_audit_logs()
    print(f"Retrieved {len(logs)} audit logs from the database:\n")
    for log in logs:
        print(f"[{log['timestamp']}] Mandate: {log['mandate_id']} | Request: \"{log['buyer_request']}\"")
        print(f"  Intent: {log['intent_quantity']}x '{log['intent_item']}' (Total: Rs. {log['intent_total']:.2f})")
        print(f"  Decision: {log['decision']} | Reason: {log['reason']}")
        print("-" * 50)
    print("")

if __name__ == "__main__":
    run_day2_tests()
