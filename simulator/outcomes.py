import numpy as np
from typing import Tuple, Optional
from domain.enums import FailureCode, CustomerSegment
from domain.models import PotentialOutcome

def generate_latent_propensities(
    rng: np.random.Generator,
    segment: CustomerSegment,
    failure_code: FailureCode,
    amount: float,
    scenario_boost: float = 0.0,
    heterogeneity_sigma: float = 0.15,
) -> Tuple[float, float, float, float]:
    """
    Generates hidden latent propensities for a customer case:
    1. natural payment propensity
    2. response propensity
    3. p2p fulfillment reliability
    4. friction sensitivity
    """
    # Segment baselines
    seg_bias = {
        CustomerSegment.VIP: 0.20,
        CustomerSegment.STANDARD: 0.0,
        CustomerSegment.NEW: -0.05,
        CustomerSegment.AT_RISK: -0.20,
    }.get(segment, 0.0)

    # Failure code natural recovery adjustments
    # e.g., Gateway downtime often self-resolves quickly; Card expired rarely self-resolves
    fail_bias = {
        FailureCode.GATEWAY_DOWNTIME: 0.25,
        FailureCode.NETWORK_TIMEOUT: 0.20,
        FailureCode.AUTHENTICATION_FAILED: 0.05,
        FailureCode.USER_DROPPED: 0.0,
        FailureCode.INSUFFICIENT_FUNDS: -0.15,
        FailureCode.CARD_EXPIRED: -0.30,
    }.get(failure_code, 0.0)

    # Amount penalty: larger amounts have slightly lower natural completion
    amount_penalty = np.clip(np.log10(max(amount, 100.0)) * 0.04 - 0.08, 0.0, 0.15)

    base_propensity = 0.25 + seg_bias + fail_bias - amount_penalty + scenario_boost
    base_propensity += rng.normal(0, heterogeneity_sigma)
    p_natural = float(np.clip(base_propensity, 0.01, 0.95))

    # Response propensity (willingness to interact with notifications)
    resp_base = 0.40 + (0.15 if segment == CustomerSegment.VIP else 0.0) + rng.normal(0, 0.1)
    p_response = float(np.clip(resp_base, 0.05, 0.95))

    # P2P reliability (if they make a promise, will they fulfill it?)
    p2p_base = 0.55 + seg_bias * 0.5 + rng.normal(0, 0.12)
    p_p2p_rel = float(np.clip(p2p_base, 0.10, 0.95))

    # Friction sensitivity (irritation per automated message)
    friction_base = 0.20 + (0.15 if segment == CustomerSegment.AT_RISK else 0.0) + rng.normal(0, 0.08)
    p_friction = float(np.clip(friction_base, 0.05, 0.80))

    return p_natural, p_response, p_p2p_rel, p_friction

def generate_potential_outcomes(
    case_id: str,
    rng: np.random.Generator,
    p_natural: float,
    p_response: float,
    p_p2p_rel: float,
    p_friction: float,
    failure_code: FailureCode,
    uplift_multiplier: float = 1.0,
) -> PotentialOutcome:
    """
    Computes hidden counterfactual potential outcomes for all actions:
    Y(control), Y(reminder), Y(payment_link), Y(promise_to_pay), Y(escalate)
    """
    # 1. Control (natural recovery without outreach)
    draw_ctrl = rng.random()
    y_ctrl = bool(draw_ctrl < p_natural)
    time_ctrl = float(rng.exponential(scale=18.0)) if y_ctrl else None
    if time_ctrl is not None:
        time_ctrl = float(np.clip(time_ctrl, 0.5, 72.0))

    # 2. Reminder: Reminds user, effective if user dropped or auth failed
    fail_reminder_uplift = {
        FailureCode.USER_DROPPED: 0.22,
        FailureCode.AUTHENTICATION_FAILED: 0.16,
        FailureCode.NETWORK_TIMEOUT: 0.12,
        FailureCode.GATEWAY_DOWNTIME: 0.10,
        FailureCode.INSUFFICIENT_FUNDS: 0.04,
        FailureCode.CARD_EXPIRED: 0.01,
    }.get(failure_code, 0.08)
    p_reminder = np.clip(p_natural + (fail_reminder_uplift * p_response * uplift_multiplier), 0.0, 0.98)
    y_reminder = bool(rng.random() < p_reminder)
    time_reminder = float(np.clip(rng.exponential(scale=12.0), 0.5, 48.0)) if y_reminder else None

    # 3. Payment Link: New fresh payment attempt mechanism, very effective for expired cards/auth failures
    fail_link_uplift = {
        FailureCode.CARD_EXPIRED: 0.35,
        FailureCode.AUTHENTICATION_FAILED: 0.28,
        FailureCode.GATEWAY_DOWNTIME: 0.25,
        FailureCode.NETWORK_TIMEOUT: 0.22,
        FailureCode.USER_DROPPED: 0.18,
        FailureCode.INSUFFICIENT_FUNDS: 0.08,
    }.get(failure_code, 0.18)
    p_link = np.clip(p_natural + (fail_link_uplift * p_response * uplift_multiplier), 0.0, 0.98)
    y_link = bool(rng.random() < p_link)
    time_link = float(np.clip(rng.exponential(scale=8.0), 0.2, 36.0)) if y_link else None

    # 4. Promise-to-Pay: Offers grace period; exceptionally effective for INSUFFICIENT_FUNDS
    fail_p2p_uplift = {
        FailureCode.INSUFFICIENT_FUNDS: 0.38,
        FailureCode.USER_DROPPED: 0.15,
        FailureCode.AUTHENTICATION_FAILED: 0.10,
        FailureCode.CARD_EXPIRED: 0.05,
        FailureCode.GATEWAY_DOWNTIME: 0.05,
        FailureCode.NETWORK_TIMEOUT: 0.05,
    }.get(failure_code, 0.10)
    p_p2p = np.clip(p_natural + (fail_p2p_uplift * p_p2p_rel * uplift_multiplier), 0.0, 0.98)
    y_p2p = bool(rng.random() < p_p2p)
    # Promise to pay settlement usually aligns with promise date (e.g. 24-72h later)
    time_p2p = float(np.clip(24.0 + rng.exponential(scale=16.0), 12.0, 96.0)) if y_p2p else None

    # 5. Escalate: Human support agent contacts customer, highest touch, high conversion across issues
    p_escalate = np.clip(p_natural + (0.35 * uplift_multiplier), 0.0, 0.99)
    y_escalate = bool(rng.random() < p_escalate)
    time_escalate = float(np.clip(rng.exponential(scale=14.0), 1.0, 60.0)) if y_escalate else None

    return PotentialOutcome(
        case_id=case_id,
        latent_payment_propensity=p_natural,
        latent_response_propensity=p_response,
        latent_p2p_reliability=p_p2p_rel,
        latent_friction_sensitivity=p_friction,
        y_control=y_ctrl,
        y_reminder=y_reminder,
        y_payment_link=y_link,
        y_promise_to_pay=y_p2p,
        y_escalate=y_escalate,
        recovery_time_hours_control=time_ctrl,
        recovery_time_hours_reminder=time_reminder,
        recovery_time_hours_payment_link=time_link,
        recovery_time_hours_promise_to_pay=time_p2p,
        recovery_time_hours_escalate=time_escalate,
    )
