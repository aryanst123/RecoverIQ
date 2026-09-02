from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, field_validator

class CustomerIntent(str, Enum):
    NEEDS_TIME = "NEEDS_TIME"
    DISPUTE = "DISPUTE"
    FINANCIAL_CONSTRAINT = "FINANCIAL_CONSTRAINT"
    PAYMENT_UNABLE = "PAYMENT_UNABLE"
    ALREADY_PAID_CLAIM = "ALREADY_PAID_CLAIM"
    STOP_REQUEST = "STOP_REQUEST"
    UNCLEAR = "UNCLEAR"

class WillingnessLevel(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    REFUSAL = "REFUSAL"
    UNKNOWN = "UNKNOWN"

class PaymentConstraint(str, Enum):
    SALARY_TIMING = "SALARY_TIMING"
    BANK_ISSUE = "BANK_ISSUE"
    LIQUIDITY_SHORT = "LIQUIDITY_SHORT"
    TECHNICAL_GLITCH = "TECHNICAL_GLITCH"
    DISPUTED_CHARGE = "DISPUTED_CHARGE"
    NONE = "NONE"

class AmbiguityState(str, Enum):
    CONFIRMED = "CONFIRMED"
    TENTATIVE = "TENTATIVE"
    AMBIGUOUS = "AMBIGUOUS"
    CONTRADICTORY = "CONTRADICTORY"

class ExtractionProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    extractor_version: str = "llm-extract-v1"
    prompt_version: str = "p2p-prompt-v1"
    source_message_length: int
    extracted_at: datetime

class RecoveryContextExtraction(BaseModel):
    """
    STRICT MINIMUM PYDANTIC SCHEMA FOR LLM EXTRACTION.
    Zero execution privileges. Contains purely structured customer context.
    Protected by frozen=True and extra='forbid'.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: CustomerIntent = CustomerIntent.UNCLEAR
    willingness_to_pay: WillingnessLevel = WillingnessLevel.UNKNOWN
    promise_exists: bool = False
    promised_date: Optional[date] = None
    payment_constraint: Optional[PaymentConstraint] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_span: Optional[str] = Field(default=None, max_length=300)
    ambiguity_state: AmbiguityState = AmbiguityState.AMBIGUOUS
    is_fallback: bool = False
    fallback_reason: Optional[str] = None
    provenance: Optional[ExtractionProvenance] = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError(f"Confidence must be bounded in [0.0, 1.0], got {v}")
        return round(float(v), 4)

    @classmethod
    def create_fallback(cls, reason: str, message: str = "") -> RecoveryContextExtraction:
        """Deterministic safe fallback object when LLM extraction fails or is unavailable."""
        return cls(
            intent=CustomerIntent.UNCLEAR,
            willingness_to_pay=WillingnessLevel.UNKNOWN,
            promise_exists=False,
            promised_date=None,
            payment_constraint=None,
            confidence=0.0,
            evidence_span=None,
            ambiguity_state=AmbiguityState.AMBIGUOUS,
            is_fallback=True,
            fallback_reason=reason,
            provenance=ExtractionProvenance(
                extractor_version="llm-extract-v1-fallback",
                prompt_version="none",
                source_message_length=len(message),
                extracted_at=datetime.utcnow(),
            ),
        )
