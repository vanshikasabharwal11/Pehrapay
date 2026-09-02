import os
import json
import re
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load env variables from backend directory or current directory
load_dotenv()
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

class ParsedIntent(BaseModel):
    item: str = Field(..., description="The exact product name matched from the catalog.")
    price: float = Field(..., description="The unit price of the product.")
    quantity: int = Field(..., description="The quantity of the product to purchase.")
    merchant_id: str = Field(..., description="The merchant ID associated with the product.")

class AgentParser:
    def __init__(self):
        self.last_call_fallback = False
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key and "AQ." in self.api_key or len(self.api_key) > 10:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel("gemini-3.5-flash")
                self.client_enabled = True
                print("Gemini client successfully initialized.")
            except ImportError:
                print("Warning: 'google-generativeai' package not installed. Running in mock mode.")
                self.client_enabled = False
            except Exception as e:
                print(f"Warning: Failed to initialize Gemini Client: {e}")
                self.client_enabled = False
        else:
            print("Warning: GEMINI_API_KEY is missing or invalid. Running in MOCK mode.")
            self.client_enabled = False

    def parse_buyer_request(self, buyer_request: str, catalog: list) -> dict:
        """
        Parses a natural-language buyer request against a product catalog.
        Returns a structured dictionary matching ParsedIntent schema.
        """
        self.last_call_fallback = not self.client_enabled
        if self.client_enabled:
            return self._parse_with_gemini(buyer_request, catalog)
        else:
            return self._parse_mock(buyer_request, catalog)

    def _parse_with_gemini(self, buyer_request: str, catalog: list) -> dict:
        import google.generativeai as genai
        
        system_instruction = (
            "You are an AI Shopping Assistant. Your task is to match the user's natural language request "
            "to exactly one product in the provided catalog and return a structured JSON object. "
            "You must populate all fields in the response schema based on the matched catalog product. "
            "If the request does not specify a quantity, default to 1."
        )

        catalog_str = json.dumps(catalog, indent=2)
        prompt = (
            f"{system_instruction}\n\n"
            f"Catalog:\n{catalog_str}\n\n"
            f"User Request: \"{buyer_request}\"\n\n"
            f"Extract the structured intent matching the schema."
        )

        import time as pytime

        max_retries = 3
        backoff_delay = 5.0

        for attempt in range(max_retries):
            try:
                # Call Gemini using GenerationConfig with response_schema
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                        response_schema=ParsedIntent,
                        temperature=0.0
                    )
                )
                
                response_text = response.text.strip()
                intent = json.loads(response_text)
                
                # Authoritative catalog price override (Ignore LLM price output)
                matched_item = None
                for item in catalog:
                    if item["name"].lower() == intent.get("item", "").lower():
                        matched_item = item
                        break
                if not matched_item:
                    for item in catalog:
                        if item["name"].lower() in intent.get("item", "").lower() or intent.get("item", "").lower() in item["name"].lower():
                            matched_item = item
                            break
                if matched_item:
                    intent["price"] = float(matched_item["price"])
                    intent["item"] = matched_item["name"]
                    intent["merchant_id"] = matched_item["merchant_id"]
                
                return intent
            except Exception as e:
                is_429 = "429" in str(e) or "ResourceExhausted" in type(e).__name__ or "quota" in str(e).lower()
                if is_429 and attempt < max_retries - 1:
                    wait_time = backoff_delay * (2 ** attempt)
                    print(f"[RETRY] Gemini API returned 429 (quota exceeded). Retrying in {wait_time:.1f} seconds... (Attempt {attempt+1}/{max_retries})")
                    pytime.sleep(wait_time)
                else:
                    print(f"[WARNING] LLM fallback active - real Gemini call failed. Error: {e}")
                    self.last_call_fallback = True
                    return self._parse_mock(buyer_request, catalog)

    def _parse_mock(self, buyer_request: str, catalog: list) -> dict:
        """
        A simple regex-based matcher to allow running without API keys or on API failures.
        """
        buyer_request_lower = buyer_request.lower()
        
        # Try to find quantity (e.g., "2", "two", "three", "10")
        quantity = 1
        qty_match = re.search(r'\b(\d+)\b', buyer_request_lower)
        if qty_match:
            quantity = int(qty_match.group(1))
        else:
            word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            for word, num in word_to_num.items():
                if word in buyer_request_lower:
                    quantity = num
                    break

        # Match product name keywords
        best_match = None
        max_overlap = 0
        
        for product in catalog:
            prod_name_lower = product["name"].lower()
            # Simple keyword matching: count how many words from the product name are in the request
            prod_words = set(re.findall(r'\w+', prod_name_lower))
            req_words = set(re.findall(r'\w+', buyer_request_lower))
            overlap = len(prod_words.intersection(req_words))
            
            if overlap > max_overlap:
                max_overlap = overlap
                best_match = product
                
        # If no keywords matched, default to the first product
        if not best_match or max_overlap == 0:
            best_match = catalog[0]
            
        print(f"[MOCK] Parsed request '{buyer_request}' -> matched product: '{best_match['name']}', qty: {quantity}")
        return {
            "item": best_match["name"],
            "price": best_match["price"],
            "quantity": quantity,
            "merchant_id": best_match["merchant_id"]
        }
