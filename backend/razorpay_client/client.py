import os
import razorpay
from dotenv import load_dotenv

# Load env variables from backend directory or current directory
load_dotenv()
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

class RazorpayClientWrapper:
    def __init__(self):
        self.key_id = os.getenv("RAZORPAY_KEY_ID")
        self.key_secret = os.getenv("RAZORPAY_KEY_SECRET")
        
        self.fallback_active = False
        # Initialize client if keys are present and not placeholders
        if self.key_id and self.key_secret and "rzp_test_" in self.key_id and "*" not in self.key_secret:
            try:
                self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
                print("Razorpay Client successfully initialized in TEST mode.")
            except Exception as e:
                print(f"Warning: Failed to initialize Razorpay Client: {e}")
                self.client = None
                self.fallback_active = True
        else:
            print("Warning: Razorpay Key ID or Secret is missing or invalid. Client will run in MOCK mode.")
            self.client = None
            self.fallback_active = True

    def create_order(self, amount_in_rupees: float, receipt_id: str = None) -> dict:
        """
        Creates an order in Razorpay.
        Amount must be provided in Rupees (will be converted to Paise internally).
        """
        self.fallback_active = False
        amount_paise = int(amount_in_rupees * 100)
        # Unique receipt ID if not provided
        receipt = receipt_id or f"receipt_{os.urandom(4).hex()}"
        
        if self.client:
            try:
                data = {
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": receipt,
                    "notes": {
                        "integration": "PehraPay",
                        "environment": "test"
                    }
                }
                order = self.client.order.create(data=data)
                return {
                    "order_id": order["id"],
                    "amount": order["amount"] / 100.0,
                    "currency": order["currency"],
                    "status": order["status"],
                    "receipt": order["receipt"]
                }
            except Exception as e:
                print(f"Warning: Razorpay order creation failed ({e}). Falling back to MOCK mode.")
                self.fallback_active = True
                mock_order_id = f"order_mock_{os.urandom(8).hex()}"
                return {
                    "order_id": mock_order_id,
                    "amount": amount_in_rupees,
                    "currency": "INR",
                    "status": "created",
                    "receipt": receipt
                }
        else:
            # Return a mock order for testing
            self.fallback_active = True
            mock_order_id = f"order_mock_{os.urandom(8).hex()}"
            print(f"[MOCK] Created Razorpay order {mock_order_id} for Rs. {amount_in_rupees:.2f}")
            return {
                "order_id": mock_order_id,
                "amount": amount_in_rupees,
                "currency": "INR",
                "status": "created",
                "receipt": receipt
            }

    def generate_payment_link(self, order_id: str, amount_in_rupees: float, description: str) -> str:
        """
        Generates a Payment Link associated with the order.
        """
        amount_paise = int(amount_in_rupees * 100)
        
        if self.client:
            try:
                data = {
                    "amount": amount_paise,
                    "currency": "INR",
                    "accept_partial": False,
                    "description": description[:200], # Razorpay description length limit
                    "reference_id": order_id,
                    "customer": {
                        "name": "PehraPay Buyer",
                        "email": "buyer@pehrapay.local",
                        "contact": "+919876543210"
                    },
                    "notify": {
                        "sms": False,
                        "email": True
                    }
                }
                payment_link = self.client.payment_link.create(data=data)
                return payment_link["short_url"]
            except Exception as e:
                print(f"Warning: Razorpay payment link creation failed ({e}). Falling back to MOCK link.")
                self.fallback_active = True
                mock_url = f"https://rzp.io/i/mock_{order_id}"
                return mock_url
        else:
            self.fallback_active = True
            mock_url = f"https://rzp.io/i/mock_{order_id}"
            print(f"[MOCK] Generated payment link for order {order_id}: {mock_url}")
            return mock_url
