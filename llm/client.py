import abc
import re
import json
import time
from datetime import date, datetime, timedelta
from typing import Tuple, Dict, Any, Optional

from llm.schema import CustomerIntent, WillingnessLevel, PaymentConstraint, AmbiguityState

class LLMClientInterface(abc.ABC):
    """Abstract interface for LLM extraction clients."""
    @abc.abstractmethod
    def generate_extraction_raw(
        self,
        system_prompt: str,
        user_prompt: str,
        customer_message: str,
        reference_date: date,
    ) -> Tuple[str, float, int]:
        """
        Returns: (raw_json_response, latency_seconds, estimated_tokens)
        """
        pass

class DeterministicMockLLMClient(LLMClientInterface):
    """
    DETERMINISTIC LLM EXTRACTION CLIENT.
    Provides byte-for-byte reproducible NLP extraction for tests and scientific benchmarks.
    Simulates real-world LLM parsing of natural language, relative dates, intent, and constraints.
    Robust against prompt injection by parsing semantic message text as data.
    """
    def __init__(self, simulated_latency_ms: float = 15.0):
        self.simulated_latency_ms = simulated_latency_ms

    def _resolve_relative_date(self, text: str, ref_date: date) -> Optional[date]:
        lower = text.lower()
        days_of_week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

        # Check 'tomorrow'
        if "tomorrow" in lower:
            return ref_date + timedelta(days=1)
        if "day after tomorrow" in lower:
            return ref_date + timedelta(days=2)

        # Check 'in X days'
        match_in_days = re.search(r"in\s+(\d+)\s+days?", lower)
        if match_in_days:
            return ref_date + timedelta(days=int(match_in_days.group(1)))

        # Check explicit day names: e.g. "by friday", "on friday"
        for i, d_name in enumerate(days_of_week):
            if d_name in lower:
                current_weekday = ref_date.weekday() # 0 = Monday, 6 = Sunday
                target_weekday = i
                days_ahead = target_weekday - current_weekday
                if days_ahead <= 0: # Target day already occurred this week, move to next week
                    days_ahead += 7
                return ref_date + timedelta(days=days_ahead)

        # Check explicit calendar date: e.g. "2026-03-15" or "15th"
        iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if iso_match:
            try:
                return datetime.strptime(iso_match.group(1), "%Y-%m-%d").date()
            except ValueError:
                pass

        day_num_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-zA-Z]+)\b", lower)
        if day_num_match:
            try:
                d_num = int(day_num_match.group(1))
                m_str = day_num_match.group(2)[:3]
                months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
                if m_str in months:
                    m_num = months.index(m_str) + 1
                    year = ref_date.year
                    # If date is in the past, roll forward
                    cand_date = date(year, m_num, d_num)
                    if cand_date < ref_date:
                        cand_date = date(year + 1, m_num, d_num)
                    return cand_date
            except Exception:
                pass

        return None

    def generate_extraction_raw(
        self,
        system_prompt: str,
        user_prompt: str,
        customer_message: str,
        reference_date: date,
    ) -> Tuple[str, float, int]:
        start_time = time.time()
        lower = customer_message.lower().strip()
        tokens = len(system_prompt.split()) + len(user_prompt.split()) + len(customer_message.split())

        # 1. Adversarial Injection Detection: Text treated as data
        # If the text explicitly tries to jailbreak or instruct system, the intent is flagged appropriately
        if "ignore previous instructions" in lower or "system says" in lower:
            # Treats it as conversational refusal or adversarial attempt
            result = {
                "intent": CustomerIntent.UNCLEAR.value,
                "willingness_to_pay": WillingnessLevel.UNKNOWN.value,
                "promise_exists": False,
                "promised_date": None,
                "payment_constraint": None,
                "confidence": 0.30,
                "evidence_span": customer_message[:100],
                "ambiguity_state": AmbiguityState.AMBIGUOUS.value,
            }
            latency = time.time() - start_time + (self.simulated_latency_ms / 1000.0)
            return json.dumps(result), latency, tokens

        # 2. Stop / Opt-out requests
        if any(w in lower for w in ["stop", "unsubscribe", "don't contact me", "do not message", "leave me alone"]):
            result = {
                "intent": CustomerIntent.STOP_REQUEST.value,
                "willingness_to_pay": WillingnessLevel.REFUSAL.value,
                "promise_exists": False,
                "promised_date": None,
                "payment_constraint": None,
                "confidence": 0.95,
                "evidence_span": customer_message[:150],
                "ambiguity_state": AmbiguityState.CONFIRMED.value,
            }
            latency = time.time() - start_time + (self.simulated_latency_ms / 1000.0)
            return json.dumps(result), latency, tokens

        # 3. Claims of already paid
        if any(w in lower for w in ["already paid", "money deducted", "debited from my account", "already cleared"]):
            result = {
                "intent": CustomerIntent.ALREADY_PAID_CLAIM.value,
                "willingness_to_pay": WillingnessLevel.UNKNOWN.value,
                "promise_exists": False,
                "promised_date": None,
                "payment_constraint": PaymentConstraint.BANK_ISSUE.value,
                "confidence": 0.90,
                "evidence_span": customer_message[:150],
                "ambiguity_state": AmbiguityState.CONFIRMED.value,
            }
            latency = time.time() - start_time + (self.simulated_latency_ms / 1000.0)
            return json.dumps(result), latency, tokens

        # 4. Dispute
        if any(w in lower for w in ["dispute", "fraud", "did not order", "wrong charge", "scam"]):
            result = {
                "intent": CustomerIntent.DISPUTE.value,
                "willingness_to_pay": WillingnessLevel.REFUSAL.value,
                "promise_exists": False,
                "promised_date": None,
                "payment_constraint": PaymentConstraint.DISPUTED_CHARGE.value,
                "confidence": 0.92,
                "evidence_span": customer_message[:150],
                "ambiguity_state": AmbiguityState.CONFIRMED.value,
            }
            latency = time.time() - start_time + (self.simulated_latency_ms / 1000.0)
            return json.dumps(result), latency, tokens

        # 5. Promise-to-Pay / Needs Time
        promised_d = self._resolve_relative_date(customer_message, reference_date)
        has_promise_words = any(w in lower for w in ["pay", "clear", "transfer", "settle", "send", "deposit", "process"])
        has_salary_words = any(w in lower for w in ["salary", "paycheck", "first of the month", "month end"])

        if has_promise_words or promised_d is not None or has_salary_words:
            constraint = PaymentConstraint.NONE
            if has_salary_words:
                constraint = PaymentConstraint.SALARY_TIMING
            elif "bank" in lower or "server" in lower or "otp" in lower:
                constraint = PaymentConstraint.BANK_ISSUE
            elif "money" in lower or "cash" in lower or "fund" in lower:
                constraint = PaymentConstraint.LIQUIDITY_SHORT

            if promised_d is not None:
                ambiguity = AmbiguityState.CONFIRMED if ("will" in lower or "shall" in lower or "definitely" in lower) else AmbiguityState.TENTATIVE
                result = {
                    "intent": CustomerIntent.NEEDS_TIME.value,
                    "willingness_to_pay": WillingnessLevel.HIGH.value,
                    "promise_exists": True,
                    "promised_date": promised_d.isoformat(),
                    "payment_constraint": constraint.value,
                    "confidence": 0.88 if ambiguity == AmbiguityState.CONFIRMED else 0.72,
                    "evidence_span": customer_message[:200],
                    "ambiguity_state": ambiguity.value,
                }
            else:
                # Needs time but date is ambiguous
                result = {
                    "intent": CustomerIntent.NEEDS_TIME.value,
                    "willingness_to_pay": WillingnessLevel.MODERATE.value,
                    "promise_exists": False,
                    "promised_date": None,
                    "payment_constraint": constraint.value,
                    "confidence": 0.65,
                    "evidence_span": customer_message[:150],
                    "ambiguity_state": AmbiguityState.AMBIGUOUS.value,
                }
            latency = time.time() - start_time + (self.simulated_latency_ms / 1000.0)
            return json.dumps(result), latency, tokens

        # 6. Default / Unclear
        result = {
            "intent": CustomerIntent.UNCLEAR.value,
            "willingness_to_pay": WillingnessLevel.UNKNOWN.value,
            "promise_exists": False,
            "promised_date": None,
            "payment_constraint": PaymentConstraint.NONE.value,
            "confidence": 0.40,
            "evidence_span": customer_message[:100],
            "ambiguity_state": AmbiguityState.AMBIGUOUS.value,
        }
        latency = time.time() - start_time + (self.simulated_latency_ms / 1000.0)
        return json.dumps(result), latency, tokens
