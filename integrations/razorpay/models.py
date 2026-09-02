from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from domain.enums import PaymentStatus, FailureCode

class NormalizedPaymentEvent(BaseModel):
    """
    NORMALIZED PAYMENT EVENT.
    Provider-agnostic internal representation of an authenticated inbound payment webhook.
    Eliminates leakage of provider raw payloads across the domain layer.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = "razorpay"
    provider_event_id: str
    event_type: str
    payment_id: Optional[str] = None
    order_id: Optional[str] = None
    amount: float
    currency: str = "INR"
    payment_status: PaymentStatus
    failure_code: Optional[FailureCode] = None
    failure_reason: Optional[str] = None
    event_timestamp: datetime
    raw_event_reference: str

class RazorpayPaymentLinkResponse(BaseModel):
    """Normalized response from Razorpay Payment Link API (v1)."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    link_id: str
    short_url: str
    amount: float
    currency: str = "INR"
    status: str
    reference_id: str
    created_at: datetime
    expire_by: Optional[datetime] = None

class RazorpayPaymentResponse(BaseModel):
    """Normalized response from Razorpay Payment retrieval API (v1)."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    payment_id: str
    amount: float
    currency: str = "INR"
    status: str
    order_id: Optional[str] = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    created_at: Optional[datetime] = None
