import os
import json
import time
from backend.agent.parser import AgentParser
from backend.razorpay_client.client import RazorpayClientWrapper
from backend.mandates.models import SpendingMandate

def load_catalog():
    # Construct path relative to this script
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    catalog_path = os.path.join(current_dir, "data", "catalog.json")
    with open(catalog_path, "r") as f:
        return json.load(f)

def run_day1_test():
    print("==================================================")
    print("            PEHRAPAY - DAY 1 TEST RUN             ")
    print("==================================================\n")

    # 1. Load hardcoded catalog
    print("[1] Loading product catalog...")
    catalog = load_catalog()
    print(f"    Loaded {len(catalog)} products from catalog.json.")
    
    # Show first 3 products as a sample
    print("    Sample Catalog items:")
    for item in catalog[:3]:
        print(f"      - {item['name']} | Rs. {item['price']} | Category: {item['category']} | Trust: {item['merchant_trust_level']}")
    print("")

    # 2. Define a minimal spending mandate object
    print("[2] Defining sample spending mandate...")
    sample_mandate = SpendingMandate(
        purpose="Office pantry snacks and beverages",
        max_amount=2000.0,
        allowed_category="groceries",
        allowed_merchant_trust_level=3.0,
        max_transactions=3,
        expiry_timestamp=int(time.time()) + 3600  # Expires in 1 hour
    )
    print(json.dumps(sample_mandate.model_dump(), indent=4))
    print("")

    # 3. Buyer natural-language request
    buyer_request = "I want to buy 2 boxes of organic green tea please."
    print(f"[3] Buyer Request: \"{buyer_request}\"\n")

    # 4. Run LLM parsing
    print("[4] Executing LLM parsing (intent extraction)...")
    parser = AgentParser()
    intent = parser.parse_buyer_request(buyer_request, catalog)
    
    print("\n    Extracted Structured Intent:")
    print(json.dumps(intent, indent=4))
    print("")

    # 5. Execute Razorpay plumbing (Order & Payment Link generation)
    print("[5] Executing Razorpay plumbing...")
    rzp = RazorpayClientWrapper()
    
    # Calculate total price
    total_price = intent["price"] * intent["quantity"]
    description = f"Purchase: {intent['quantity']}x {intent['item']}"
    
    print(f"    Creating order for {description} totaling Rs. {total_price:.2f}...")
    try:
        # Create Razorpay Order
        order_res = rzp.create_order(amount_in_rupees=total_price)
        print(f"    Razorpay Order Created: {order_res['order_id']} (Status: {order_res['status']})")
        
        # Generate Payment Link
        payment_link = rzp.generate_payment_link(
            order_id=order_res["order_id"],
            amount_in_rupees=total_price,
            description=description
        )
        print(f"    Razorpay Payment Link Generated: {payment_link}")
        
    except Exception as e:
        print(f"    ERROR: Razorpay integration failed: {e}")
        
    print("\n==================================================")
    print("           DAY 1 PLUMBING VERIFIED SUCCESS        ")
    print("==================================================")

if __name__ == "__main__":
    run_day1_test()
