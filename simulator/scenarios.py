from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class ScenarioConfig:
    scenario_id: str
    name: str
    description: str
    natural_recovery_boost: float = 0.0
    uplift_multiplier: float = 1.0
    heterogeneity_sigma: float = 0.15
    execution_failure_rate: float = 0.0
    execution_timeout_rate: float = 0.0

SCENARIOS: Dict[str, ScenarioConfig] = {
    "S1_HIGH_NATURAL_RECOVERY": ScenarioConfig(
        scenario_id="S1_HIGH_NATURAL_RECOVERY",
        name="High Natural Recovery",
        description="Customers have high latent probability of recovering on their own; interventions risk wasting budget.",
        natural_recovery_boost=0.30,
        uplift_multiplier=0.8,
        heterogeneity_sigma=0.12,
    ),
    "S2_LOW_NATURAL_RECOVERY": ScenarioConfig(
        scenario_id="S2_LOW_NATURAL_RECOVERY",
        name="Low Natural Recovery",
        description="Customers rarely self-recover; intelligent recovery outreach is necessary to capture revenue.",
        natural_recovery_boost=-0.20,
        uplift_multiplier=1.2,
        heterogeneity_sigma=0.15,
    ),
    "S3_WEAK_INTERVENTION_EFFECT": ScenarioConfig(
        scenario_id="S3_WEAK_INTERVENTION_EFFECT",
        name="Weak Intervention Effect",
        description="Interventions have minimal uplift over control; economic policy must be conservative to prevent negative net return.",
        natural_recovery_boost=0.0,
        uplift_multiplier=0.25,
        heterogeneity_sigma=0.15,
    ),
    "S4_STRONG_INTERVENTION_EFFECT": ScenarioConfig(
        scenario_id="S4_STRONG_INTERVENTION_EFFECT",
        name="Strong Intervention Effect",
        description="High responsiveness to outreach; timely reminders and payment links yield large gains.",
        natural_recovery_boost=0.0,
        uplift_multiplier=2.2,
        heterogeneity_sigma=0.15,
    ),
    "S5_HIGH_RECOVERY_HETEROGENEITY": ScenarioConfig(
        scenario_id="S5_HIGH_RECOVERY_HETEROGENEITY",
        name="High Heterogeneity",
        description="Massive variance in customer sensitivity and channel responsiveness; adaptive ranking has highest advantage.",
        natural_recovery_boost=0.0,
        uplift_multiplier=1.0,
        heterogeneity_sigma=0.40,
    ),
    "S6_HIGH_EVENT_FAILURE_RATE": ScenarioConfig(
        scenario_id="S6_HIGH_EVENT_FAILURE_RATE",
        name="Adversarial Execution Environment",
        description="Frequent gateway timeouts, dropped webhooks, and ambiguous action states testing system resilience.",
        natural_recovery_boost=0.0,
        uplift_multiplier=1.0,
        heterogeneity_sigma=0.15,
        execution_failure_rate=0.20,
        execution_timeout_rate=0.15,
    ),
}

def get_scenario(scenario_id: str) -> ScenarioConfig:
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario_id}'. Available: {list(SCENARIOS.keys())}")
    return SCENARIOS[scenario_id]
