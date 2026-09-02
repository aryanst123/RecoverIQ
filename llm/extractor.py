import json
import logging
from datetime import date, datetime, timezone
from typing import Optional, Tuple, Dict, Any

from pydantic import ValidationError
from llm.schema import (
    RecoveryContextExtraction,
    ExtractionProvenance,
    AmbiguityState,
    CustomerIntent,
)
from llm.prompts import SYSTEM_INSTRUCTION, EXTRACTION_USER_TEMPLATE, PROMPT_VERSION
from llm.client import LLMClientInterface, DeterministicMockLLMClient

logger = logging.getLogger(__name__)

class LLMContextExtractor:
    """
    LLM CONTEXT EXTRACTION SERVICE.
    Transforms unstructured customer inbound text into strictly validated,
    immutable Pydantic structured recovery context (RecoveryContextExtraction).
    STRICT BOUNDARY: Zero execution privileges. Zero gateway connections.
    """
    def __init__(
        self,
        client: Optional[LLMClientInterface] = None,
        extractor_version: str = "llm-extract-v1",
    ):
        self.client = client or DeterministicMockLLMClient()
        self.extractor_version = extractor_version
        self.metrics = {
            "total_calls": 0,
            "successful_extractions": 0,
            "validation_failures": 0,
            "fallbacks_invoked": 0,
            "total_latency_seconds": 0.0,
            "total_tokens_estimated": 0,
        }

    def extract_context(
        self,
        customer_message: str,
        reference_time: Optional[datetime] = None,
    ) -> RecoveryContextExtraction:
        """
        Extracts structured recovery context from a raw customer message.
        Always returns a valid RecoveryContextExtraction (never raises on bad input).
        """
        self.metrics["total_calls"] += 1
        ref_dt = reference_time or datetime.now(timezone.utc)
        ref_date = ref_dt.date() if isinstance(ref_dt, datetime) else ref_dt

        # Handle empty or non-string message safely
        if not customer_message or not isinstance(customer_message, str) or not customer_message.strip():
            self.metrics["fallbacks_invoked"] += 1
            return RecoveryContextExtraction.create_fallback(
                reason="EMPTY_OR_INVALID_INPUT_TEXT",
                message="",
            )

        sanitized_msg = customer_message.strip()
        ref_day_name = ref_date.strftime("%A")

        user_prompt = EXTRACTION_USER_TEMPLATE.format(
            reference_date=ref_date.isoformat(),
            reference_day_name=ref_day_name,
            customer_message=sanitized_msg,
        )

        try:
            raw_response, latency, tokens = self.client.generate_extraction_raw(
                system_prompt=SYSTEM_INSTRUCTION,
                user_prompt=user_prompt,
                customer_message=sanitized_msg,
                reference_date=ref_date,
            )
            self.metrics["total_latency_seconds"] += latency
            self.metrics["total_tokens_estimated"] += tokens
        except Exception as e:
            logger.warning(f"LLM Client error during extraction: {e}")
            self.metrics["fallbacks_invoked"] += 1
            return RecoveryContextExtraction.create_fallback(
                reason=f"LLM_CLIENT_ERROR: {type(e).__name__}",
                message=sanitized_msg,
            )

        # Parse JSON and validate through Pydantic
        try:
            parsed_dict = json.loads(raw_response)
        except json.JSONDecodeError as err:
            logger.warning(f"Malformed JSON from LLM: {err}")
            self.metrics["validation_failures"] += 1
            self.metrics["fallbacks_invoked"] += 1
            return RecoveryContextExtraction.create_fallback(
                reason=f"JSON_DECODE_ERROR: {str(err)}",
                message=sanitized_msg,
            )

        try:
            provenance = ExtractionProvenance(
                extractor_version=self.extractor_version,
                prompt_version=PROMPT_VERSION,
                source_message_length=len(sanitized_msg),
                extracted_at=datetime.now(timezone.utc),
            )
            parsed_dict["provenance"] = provenance

            extraction = RecoveryContextExtraction(**parsed_dict)

            # Domain sanity checks on extracted dates
            if extraction.promised_date is not None:
                # 1. Past date check
                if extraction.promised_date < ref_date:
                    # Date in the past is contradictory
                    extraction = extraction.model_copy(update={
                        "ambiguity_state": AmbiguityState.CONTRADICTORY,
                        "promise_exists": False,
                    })
                # 2. Beyond 30-day recovery window
                elif (extraction.promised_date - ref_date).days > 30:
                    extraction = extraction.model_copy(update={
                        "ambiguity_state": AmbiguityState.AMBIGUOUS,
                        "promise_exists": False,
                    })

            self.metrics["successful_extractions"] += 1
            return extraction

        except ValidationError as val_err:
            logger.warning(f"Pydantic schema validation error: {val_err}")
            self.metrics["validation_failures"] += 1
            self.metrics["fallbacks_invoked"] += 1
            return RecoveryContextExtraction.create_fallback(
                reason=f"SCHEMA_VALIDATION_ERROR: {str(val_err)[:150]}",
                message=sanitized_msg,
            )
