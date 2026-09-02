import os
import sys
import razorpay
from dotenv import load_dotenv

# Ensure stdout uses UTF-8 to prevent cp1252 encoding crashes on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_razorpay_auth():
    print("==================================================")
    print("       PEHRAPAY - RAZORPAY AUTH ISOLATION TEST    ")
    print("==================================================")
    
    # 1. Load env variables
    load_dotenv()
    # Also look explicitly in backend directory if run from root
    backend_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(backend_env):
        load_dotenv(dotenv_path=backend_env)
        
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    
    # 2. Print lengths and basic details
    if not key_id:
        print("[ERROR] RAZORPAY_KEY_ID is missing or not loaded from env!")
    else:
        print(f"RAZORPAY_KEY_ID loaded: length={len(key_id)}, starts with='{key_id[:8]}...' (raw length checked for spaces/truncation)")
        if key_id.strip() != key_id:
            print("[WARNING] RAZORPAY_KEY_ID contains leading or trailing whitespace!")
            
    if not key_secret:
        print("[ERROR] RAZORPAY_KEY_SECRET is missing or not loaded from env!")
    else:
        print(f"RAZORPAY_KEY_SECRET loaded: length={len(key_secret)} (raw length checked for spaces/truncation)")
        if key_secret.strip() != key_secret:
            print("[WARNING] RAZORPAY_KEY_SECRET contains leading or trailing whitespace!")

    if not key_id or not key_secret:
        print("[FAIL] Missing credentials. Cannot proceed with Razorpay API call.")
        sys.exit(1)

    # 3. Attempt simple Razorpay API order creation call directly using SDK client
    print("\nAttempting connection to Razorpay API...")
    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        
        # Try a simple order creation (100 paise = 1 INR)
        data = {
            "amount": 100,  # 1 INR in paise
            "currency": "INR",
            "receipt": "auth_test_receipt",
            "notes": {
                "test": "auth_isolation"
            }
        }
        print("Sending order.create request to Razorpay...")
        order = client.order.create(data=data)
        
        print("[SUCCESS] Razorpay authentication succeeded!")
        print(f"Created Order ID: {order.get('id')}")
        print(f"Status: {order.get('status')}")
        sys.exit(0)
    except Exception as e:
        print("[FAIL] Razorpay API call failed!")
        print("--- FULL RAW EXCEPTION FROM RAZORPAY SDK ---")
        import traceback
        traceback.print_exc()
        print("--------------------------------------------")
        sys.exit(1)

if __name__ == "__main__":
    test_razorpay_auth()
