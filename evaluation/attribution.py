from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
from evaluation.metrics import CaseEvaluationResult

@dataclass
class AttributionWindowResult:
    window_hours: int
    arm: str
    total_recovered: float
    recovery_rate: float
    net_recovered: float

@dataclass
class AttributionSensitivityReport:
    primary_window_hours: int
    windows_evaluated: List[int]
    results_by_window: Dict[int, Dict[str, AttributionWindowResult]]
    rankings_consistent: bool
    notes: str

def evaluate_attribution_sensitivity(
    case_results: List[CaseEvaluationResult],
    recovery_times_relative_hours: Dict[str, Optional[float]],
    windows: List[int] = None,
    primary_window: int = 72,
) -> AttributionSensitivityReport:
    """
    Computes attribution sensitivity across multiple post-failure observation windows
    (e.g., 24h, 72h, 168h).
    """
    if windows is None:
        windows = [24, 72, 168]

    arms = sorted(list(set(r.arm for r in case_results)))
    results_by_window: Dict[int, Dict[str, AttributionWindowResult]] = {}
    rankings_by_window: Dict[int, List[str]] = {}

    for w in windows:
        window_arm_data: Dict[str, AttributionWindowResult] = {}
        arm_nets: Dict[str, float] = {}

        for arm in arms:
            arm_cases = [r for r in case_results if r.arm == arm]
            n = len(arm_cases)
            if n == 0:
                continue

            recovered_val = 0.0
            rec_count = 0
            total_costs = sum(c.intervention_cost + c.friction_cost for c in arm_cases)

            for c in arm_cases:
                rel_hours = recovery_times_relative_hours.get(c.case_id)
                # Count as recovered in this window if recovered within w hours
                if c.recovered_amount > 0 and rel_hours is not None and rel_hours <= float(w):
                    recovered_val += c.recovered_amount
                    rec_count += 1

            net_val = recovered_val - total_costs
            arm_nets[arm] = net_val
            window_arm_data[arm] = AttributionWindowResult(
                window_hours=w,
                arm=arm,
                total_recovered=recovered_val,
                recovery_rate=float(rec_count / n),
                net_recovered=net_val,
            )

        results_by_window[w] = window_arm_data
        sorted_arms = sorted(arm_nets.keys(), key=lambda a: arm_nets[a], reverse=True)
        rankings_by_window[w] = sorted_arms

    # Check consistency of ranking across windows
    reference_ranking = rankings_by_window.get(primary_window, [])
    consistent = all(rankings_by_window[w] == reference_ranking for w in windows)

    notes = (
        "Arm rankings remain stable across all sensitivity windows."
        if consistent
        else "Sensitivity divergence: arm rankings shifted depending on attribution window length."
    )

    return AttributionSensitivityReport(
        primary_window_hours=primary_window,
        windows_evaluated=windows,
        results_by_window=results_by_window,
        rankings_consistent=consistent,
        notes=notes,
    )
