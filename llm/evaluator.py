from typing import Dict, Any, List
import numpy as np
from datetime import datetime, timezone

from llm.extractor import LLMContextExtractor
from llm.eval_dataset import get_fixed_extraction_evaluation_dataset, ExtractionEvalSample

class ExtractionEvaluator:
    """
    Evaluates extraction accuracy and schema robustness across synthetic test corpus.
    Measures:
    - Intent accuracy
    - P2P promise detection accuracy
    - Promised date accuracy
    - Constraint extraction accuracy
    - Adversarial rejection rate
    - Malformed output rate
    - Fallback rate
    """
    def __init__(self, extractor: LLMContextExtractor):
        self.extractor = extractor

    def run_evaluation(
        self,
        samples: List[ExtractionEvalSample] = None,
    ) -> Dict[str, Any]:
        eval_samples = samples or get_fixed_extraction_evaluation_dataset()
        total = len(eval_samples)
        if total == 0:
            return {}

        correct_intent = 0
        correct_p2p = 0
        correct_date = 0
        correct_constraint = 0
        adversarial_handled = 0
        adversarial_total = 0
        fallbacks = 0
        latencies = []

        for s in eval_samples:
            ref_dt = datetime.combine(s.reference_date, datetime.min.time(), tzinfo=timezone.utc)
            extraction = self.extractor.extract_context(s.customer_message, reference_time=ref_dt)

            if extraction.is_fallback:
                fallbacks += 1

            # Check intent
            if extraction.intent == s.expected_intent:
                correct_intent += 1

            # Check P2P promise detection
            if extraction.promise_exists == s.expected_promise_exists:
                correct_p2p += 1

            # Check Promised Date
            if extraction.promised_date == s.expected_promised_date:
                correct_date += 1

            # Check Constraint
            if extraction.payment_constraint == s.expected_constraint:
                correct_constraint += 1

            # Check Adversarial handling: must NOT execute, must NOT create false promises
            if s.is_adversarial:
                adversarial_total += 1
                if not extraction.promise_exists and extraction.intent != "RECOVERED":
                    adversarial_handled += 1

        metrics = {
            "evaluation_type": "SYNTHETIC_EXTRACTION_EVALUATION",
            "samples_evaluated": total,
            "intent_accuracy": round(correct_intent / total, 4),
            "p2p_detection_accuracy": round(correct_p2p / total, 4),
            "promised_date_accuracy": round(correct_date / total, 4),
            "constraint_accuracy": round(correct_constraint / total, 4),
            "adversarial_resilience_rate": round(adversarial_handled / adversarial_total, 4) if adversarial_total > 0 else 1.0,
            "fallback_rate": round(fallbacks / total, 4),
            "avg_latency_ms": round((self.extractor.metrics["total_latency_seconds"] / total) * 1000.0, 2) if total > 0 else 0.0,
            "total_tokens_estimated": self.extractor.metrics["total_tokens_estimated"],
        }
        return metrics
