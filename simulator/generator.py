import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict
from domain.enums import (
    CustomerSegment,
    ChannelPreference,
    FailureCode,
    PaymentStatus,
    CaseState,
)
from domain.models import (
    Customer,
    Payment,
    PaymentAttempt,
    RecoveryCase,
    PotentialOutcome,
)
from simulator.outcomes import generate_latent_propensities, generate_potential_outcomes
from simulator.scenarios import ScenarioConfig, get_scenario

class SyntheticCaseGenerator:
    """
    Generates synthetic failed one-time payment cases with realistic heterogeneity.
    Maintains strict reproducibility via numpy Generator seeds.
    """
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def generate_case(
        self,
        index: int,
        scenario: ScenarioConfig,
        base_time: datetime,
    ) -> Tuple[Customer, Payment, PaymentAttempt, RecoveryCase, PotentialOutcome]:
        case_id = f"case_{index:06d}"
        cust_id = f"cust_{index:06d}"
        pay_id = f"pay_{index:06d}"
        attempt_id = f"att_{index:06d}"

        # 1. Customer attributes
        seg_choices = [CustomerSegment.STANDARD, CustomerSegment.VIP, CustomerSegment.NEW, CustomerSegment.AT_RISK]
        seg_probs = [0.60, 0.15, 0.15, 0.10]
        segment = seg_choices[int(self.rng.choice(len(seg_choices), p=seg_probs))]

        chan_choices = [ChannelPreference.WHATSAPP, ChannelPreference.SMS, ChannelPreference.EMAIL]
        chan_probs = [0.60, 0.30, 0.10]
        channel = chan_choices[int(self.rng.choice(len(chan_choices), p=chan_probs))]

        # 2% opt-out rate initially
        opt_out = bool(self.rng.random() < 0.02)

        customer = Customer(
            customer_id=cust_id,
            segment=segment,
            channel_preference=channel,
            opt_out=opt_out,
            metadata={"source": "ecommerce_checkout", "loyalty_tier": segment.value},
        )

        # 2. Payment details
        # Log-normal distribution of order values in INR: median around ₹1,500 to ₹3,500
        raw_amt = float(self.rng.lognormal(mean=7.6, sigma=0.85))
        amount = float(np.round(np.clip(raw_amt, 150.0, 50000.0), 2))

        payment_created = base_time + timedelta(minutes=float(self.rng.uniform(0, 180)))
        payment = Payment(
            payment_id=pay_id,
            customer_id=cust_id,
            amount=amount,
            currency="INR",
            created_at=payment_created,
            status=PaymentStatus.FAILED,
        )

        # 3. Initial Failure Attempt
        fail_choices = [
            FailureCode.AUTHENTICATION_FAILED,
            FailureCode.INSUFFICIENT_FUNDS,
            FailureCode.GATEWAY_DOWNTIME,
            FailureCode.NETWORK_TIMEOUT,
            FailureCode.CARD_EXPIRED,
            FailureCode.USER_DROPPED,
        ]
        fail_probs = [0.35, 0.30, 0.15, 0.10, 0.05, 0.05]
        failure_code = fail_choices[int(self.rng.choice(len(fail_choices), p=fail_probs))]

        fail_reasons = {
            FailureCode.AUTHENTICATION_FAILED: "3D Secure authentication declined or OTP expired",
            FailureCode.INSUFFICIENT_FUNDS: "Debit failed due to insufficient available balance in account",
            FailureCode.GATEWAY_DOWNTIME: "Acquiring bank payment gateway temporary outage",
            FailureCode.NETWORK_TIMEOUT: "Network handshake timeout during payment session",
            FailureCode.CARD_EXPIRED: "Payment card has expired",
            FailureCode.USER_DROPPED: "User closed checkout sheet before completing PIN entry",
        }

        attempt = PaymentAttempt(
            attempt_id=attempt_id,
            payment_id=pay_id,
            failure_code=failure_code,
            failure_reason=fail_reasons[failure_code],
            attempted_at=payment_created + timedelta(seconds=float(self.rng.uniform(10, 45))),
            gateway_reference=f"gtw_ref_{self.rng.integers(100000, 999999)}",
        )

        # 4. Recovery Case
        case = RecoveryCase(
            case_id=case_id,
            payment_id=pay_id,
            customer_id=cust_id,
            current_state=CaseState.PAYMENT_FAILED,
            amount_due=amount,
            residual_amount=amount,
            created_at=attempt.attempted_at,
            last_updated_at=attempt.attempted_at,
            automated_action_count=0,
            next_eligible_at=attempt.attempted_at,
        )

        # 5. Hidden Ground Truth Potential Outcomes (Simulation only!)
        p_nat, p_resp, p_p2p, p_fric = generate_latent_propensities(
            rng=self.rng,
            segment=segment,
            failure_code=failure_code,
            amount=amount,
            scenario_boost=scenario.natural_recovery_boost,
            heterogeneity_sigma=scenario.heterogeneity_sigma,
        )

        pot_outcome = generate_potential_outcomes(
            case_id=case_id,
            rng=self.rng,
            p_natural=p_nat,
            p_response=p_resp,
            p_p2p_rel=p_p2p,
            p_friction=p_fric,
            failure_code=failure_code,
            uplift_multiplier=scenario.uplift_multiplier,
        )

        return customer, payment, attempt, case, pot_outcome

    def generate_batch(
        self,
        count: int,
        scenario_id: str = "S1_HIGH_NATURAL_RECOVERY",
        base_time: datetime = None,
    ) -> List[Tuple[Customer, Payment, PaymentAttempt, RecoveryCase, PotentialOutcome]]:
        if base_time is None:
            base_time = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        scenario = get_scenario(scenario_id)
        return [self.generate_case(i + 1, scenario, base_time) for i in range(count)]
