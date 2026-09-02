import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

@dataclass
class BootstrapResult:
    comparison: str
    point_estimate: float
    lower_bound: float
    upper_bound: float
    confidence_level: float
    bootstrap_iterations: int
    random_seed: int
    claim_classification: str
    critical_safety_violations: int

def compute_bootstrap_difference_ci(
    sample_a: List[float],
    sample_b: List[float],
    comparison_name: str = "RecoverIQ - Baseline",
    confidence_level: float = 0.95,
    iterations: int = 1000,
    seed: int = 42,
    safety_violations_arm_a: int = 0,
) -> BootstrapResult:
    """
    Computes a 95% bootstrap confidence interval for difference in mean net recovered revenue:
    Delta = Mean(Sample_A) - Mean(Sample_B).
    Uses a deterministic numpy generator seed for complete reproducibility.
    """
    arr_a = np.array(sample_a, dtype=float)
    arr_b = np.array(sample_b, dtype=float)

    n_a = len(arr_a)
    n_b = len(arr_b)

    if n_a == 0 or n_b == 0:
        return BootstrapResult(
            comparison=comparison_name,
            point_estimate=0.0,
            lower_bound=0.0,
            upper_bound=0.0,
            confidence_level=confidence_level,
            bootstrap_iterations=iterations,
            random_seed=seed,
            claim_classification="INCONCLUSIVE",
            critical_safety_violations=safety_violations_arm_a,
        )

    point_estimate = float(np.mean(arr_a) - np.mean(arr_b))

    rng = np.random.default_rng(seed)
    boot_diffs = np.empty(iterations, dtype=float)

    for i in range(iterations):
        resample_a = rng.choice(arr_a, size=n_a, replace=True)
        resample_b = rng.choice(arr_b, size=n_b, replace=True)
        boot_diffs[i] = np.mean(resample_a) - np.mean(resample_b)

    alpha = 1.0 - confidence_level
    lower_pct = 100.0 * (alpha / 2.0)
    upper_pct = 100.0 * (1.0 - alpha / 2.0)

    lower_bound = float(np.percentile(boot_diffs, lower_pct))
    upper_bound = float(np.percentile(boot_diffs, upper_pct))

    # Strict statistical claim rule
    if lower_bound > 0.0 and safety_violations_arm_a == 0:
        claim = "STATISTICALLY_SIGNIFICANT_POSITIVE"
    elif upper_bound < 0.0:
        claim = "STATISTICALLY_SIGNIFICANT_NEGATIVE"
    else:
        claim = "INCONCLUSIVE"

    return BootstrapResult(
        comparison=comparison_name,
        point_estimate=point_estimate,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        confidence_level=confidence_level,
        bootstrap_iterations=iterations,
        random_seed=seed,
        claim_classification=claim,
        critical_safety_violations=safety_violations_arm_a,
    )
