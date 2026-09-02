import os
import sys
import razorpay
from dotenv import load_dotenv

# Set stdout to UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def check_raw_error():
    load_dotenv()
    backend_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(backend_env):
        load_dotenv(dotenv_path=backend_env)
        
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    
    print("==================================================")
    # Check credentials loaded
    print(f"Key ID: {key_id}")
    print(f"Key Secret: {'*' * len(key_secret) if key_secret else 'None'}")
    print("==================================================")

    if not key_id or not key_secret:
        print("Missing credentials.")
        return

    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        
        # We will attempt to create a payment link directly
        # order_id can be any mock id since reference_id just needs to be unique
        import time
        unique_ref = f"ref_{int(time.time())}"
        
        data = {
            "amount": 100,  # 1 INR
            "currency": "INR",
            "accept_partial": False,
            "description": "Raw Razorpay Error Inspection Link",
            "reference_id": unique_ref,
            "customer": {
                "name": "PehraPay Tester",
                "email": "tester@pehrapay.local",
                "contact": "+919876543210"
            },
            "notify": {"sms": False, "email": False}
        }
        
        print("Attempting to create payment link on Razorpay server...")
        link = client.payment_link.create(data=data)
        print("SUCCESS! Link created successfully:", link.get("short_url"))
    except Exception as e:
        print("\n--- DETECTED EXCEPTION DETAILS ---")
        print(f"Exception Type: {type(e)}")
        print(f"Exception Message (str): {str(e)}")
        print(f"Exception Args: {e.args}")
        if hasattr(e, "status_code"):
            print(f"HTTP Status Code: {e.status_code}")
        if hasattr(e, "json_body"):
            print(f"JSON Body: {e.json_body}")
        print("----------------------------------")

if __name__ == "__main__":
    check_raw_error()
