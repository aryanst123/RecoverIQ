from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import numpy as np

@dataclass
class CaseEvaluationResult:
    case_id: str
    arm: str
    starting_amount: float
    recovered_amount: float
    gross_recovered: float
    intervention_cost: float
    friction_cost: float
    net_recovered: float
    actions_taken: List[str]
    final_state: str
    recovery_timestamp: Optional[str]
    attribution_classification: str # 'ATTRIBUTED', 'NATURAL', 'UNRECOVERED'
    safety_violations: List[str]
    experiment_id: str
    would_recover_naturally: bool = False # Evaluation-only ground truth check for unnecessary intervention rate

@dataclass
class ArmMetrics:
    arm: str
    case_count: int
    total_starting_amount: float
    total_gross_recovered: float
    total_intervention_cost: float
    total_friction_cost: float
    total_cost: float
    total_net_recovered: float
    mean_net_recovered: float
    std_net_recovered: float
    
    # Exactly 4 Secondary Metrics:
    recovery_rate: float
    intervention_efficiency: float
    unnecessary_intervention_rate: float
    critical_safety_violations: int
    critical_safety_violation_rate: float

def compute_arm_metrics(results: List[CaseEvaluationResult], arm_name: str) -> ArmMetrics:
    arm_results = [r for r in results if r.arm == arm_name]
    n = len(arm_results)
    if n == 0:
        return ArmMetrics(
            arm=arm_name,
            case_count=0,
            total_starting_amount=0.0,
            total_gross_recovered=0.0,
            total_intervention_cost=0.0,
            total_friction_cost=0.0,
            total_cost=0.0,
            total_net_recovered=0.0,
            mean_net_recovered=0.0,
            std_net_recovered=0.0,
            recovery_rate=0.0,
            intervention_efficiency=0.0,
            unnecessary_intervention_rate=0.0,
            critical_safety_violations=0,
            critical_safety_violation_rate=0.0,
        )

    total_start = sum(r.starting_amount for r in arm_results)
    total_gross = sum(r.gross_recovered for r in arm_results)
    total_act_cost = sum(r.intervention_cost for r in arm_results)
    total_fric_cost = sum(r.friction_cost for r in arm_results)
    total_cost = total_act_cost + total_fric_cost
    total_net = sum(r.net_recovered for r in arm_results)

    net_arr = np.array([r.net_recovered for r in arm_results], dtype=float)
    mean_net = float(np.mean(net_arr))
    std_net = float(np.std(net_arr, ddof=1)) if n > 1 else 0.0

    # 1. Recovery Rate: cases recovered / total cases
    recovered_cases = sum(1 for r in arm_results if r.recovered_amount > 0)
    rec_rate = float(recovered_cases / n)

    # 2. Intervention Efficiency: Net revenue per rupee spent on interventions
    # If total_cost is 0 (e.g. in Control), define as gross/1.0 or 0.0
    efficiency = float(total_net / max(total_cost, 1.0)) if total_cost > 0 else 0.0

    # 3. Unnecessary Intervention Rate:
    # Fraction of intervened cases that would have naturally recovered without automated intervention
    intervened_cases = [r for r in arm_results if len(r.actions_taken) > 0 and r.actions_taken != ["STOP"]]
    if intervened_cases:
        unnecessary_count = sum(1 for r in intervened_cases if r.would_recover_naturally)
        unnecessary_rate = float(unnecessary_count / len(intervened_cases))
    else:
        unnecessary_rate = 0.0

    # 4. Critical Safety Violations
    total_violations = sum(len(r.safety_violations) for r in arm_results)
    violation_rate = float(total_violations / n)

    return ArmMetrics(
        arm=arm_name,
        case_count=n,
        total_starting_amount=total_start,
        total_gross_recovered=total_gross,
        total_intervention_cost=total_act_cost,
        total_friction_cost=total_fric_cost,
        total_cost=total_cost,
        total_net_recovered=total_net,
        mean_net_recovered=mean_net,
        std_net_recovered=std_net,
        recovery_rate=rec_rate,
        intervention_efficiency=efficiency,
        unnecessary_intervention_rate=unnecessary_rate,
        critical_safety_violations=total_violations,
        critical_safety_violation_rate=violation_rate,
    )
