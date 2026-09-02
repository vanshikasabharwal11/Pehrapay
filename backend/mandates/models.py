from pydantic import BaseModel, Field
from typing import Optional

class SpendingMandate(BaseModel):
    """
    A Spending Mandate representing user-defined spending limits and risk controls.
    """
    purpose: str = Field(..., description="The purpose or description of this spending mandate.")
    max_amount: float = Field(..., description="Maximum allowed amount for a single transaction.")
    allowed_category: str = Field(..., description="The product category allowed.")
    allowed_merchant_trust_level: float = Field(..., description="The minimum merchant trust level.")
    max_transactions: int = Field(..., description="The maximum number of transactions.")
    expiry_timestamp: int = Field(..., description="Unix timestamp when this mandate expires.")
    human_review_threshold: Optional[float] = Field(None, description="Trigger human review if transaction exceeds this amount.")
