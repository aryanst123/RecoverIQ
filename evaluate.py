import argparse
import json
import os
import sys
from evaluation.runner import ExperimentRunner

def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="RecoverIQ Experimental Evaluation Harness (Track 03: AI Revenue Recovery)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/evaluation.yaml",
        help="Path to evaluation YAML configuration",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("RECOVERIQ — EXPERIMENTAL BENCHMARK HARNESS")
    print(f"Loading Configuration: {args.config}")
    print("=" * 70)

    runner = ExperimentRunner(config_path=args.config)
    results = runner.run_experiment()

    manifest = results["manifest"]
    metrics = results["metrics_by_arm"]
    bootstraps = results["bootstrap_results"]
    attribution = results["attribution_sensitivity"]

    print("\n" + "=" * 70)
    print("1. EXPERIMENT MANIFEST & INTEGRITY CHECKSUMS")
    print("=" * 70)
    print(f"Experiment ID:           {manifest.experiment_id}")
    print(f"Dataset Size:            {manifest.dataset_size:,} cases")
    print(f"Random Seed:             {manifest.seed}")
    print(f"Scenario:                {manifest.scenario_id}")
    print(f"Baseline Version:        {manifest.baseline_version}")
    print(f"Baseline Checksum:       {manifest.baseline_checksum}")
    print(f"RecoverIQ Version:       {manifest.recoveriq_version}")
    print(f"Attribution Window:      {manifest.attribution_window_hours}h")
    print("\nConfiguration Checksums:")
    for cfg_name, chk in manifest.config_checksums.items():
        print(f"  {cfg_name:12s}: {chk}")

    print("\n" + "=" * 70)
    print("2. ARM-LEVEL PERFORMANCE & SECONDARY METRICS")
    print("=" * 70)
    header = f"{'Arm':<24} | {'Cases':<6} | {'Gross Rec':<11} | {'Total Cost':<10} | {'Net Rec':<11} | {'Rec Rate':<8} | {'Efficiency':<10} | {'Unnecessary':<11} | {'Safety Viol'}"
    print(header)
    print("-" * len(header))
    for arm_name, m in metrics.items():
        print(
            f"{arm_name:<24} | "
            f"{m.case_count:<6} | "
            f"INR {m.total_gross_recovered:>7,.0f} | "
            f"INR {m.total_cost:>6,.0f} | "
            f"INR {m.total_net_recovered:>7,.0f} | "
            f"{m.recovery_rate:>7.1%} | "
            f"{m.intervention_efficiency:>9.2f}x | "
            f"{m.unnecessary_intervention_rate:>10.1%} | "
            f"{m.critical_safety_violations:>6}"
        )

    print("\n" + "=" * 70)
    print("3. PRIMARY METRIC & 95% BOOTSTRAP CONFIDENCE INTERVALS")
    print("=" * 70)
    for comp_name, b_res in bootstraps.items():
        print(f"\nComparison: {b_res.comparison}")
        print(f"  Point Estimate (Delta Net/Case): INR {b_res.point_estimate:>+8.2f}")
        print(f"  95% Bootstrap CI:               [INR {b_res.lower_bound:>+8.2f}, INR {b_res.upper_bound:>+8.2f}]")
        print(f"  Iterations:                     {b_res.bootstrap_iterations}")
        print(f"  Safety Violations:              {b_res.critical_safety_violations}")
        print(f"  Statistical Claim Decision:     {b_res.claim_classification}")

    print("\n" + "=" * 70)
    print("4. ATTRIBUTION SENSITIVITY (24h vs 72h vs 168h)")
    print("=" * 70)
    print(f"Rankings Consistent across windows: {attribution.rankings_consistent}")
    print(f"Notes: {attribution.notes}")
    for w in attribution.windows_evaluated:
        print(f"\nWindow: {w} hours post-failure")
        for arm_name, w_res in attribution.results_by_window[w].items():
            print(f"  {arm_name:<24}: Recovered: INR {w_res.total_recovered:>9,.0f} | Rec Rate: {w_res.recovery_rate:.1%} | Net: INR {w_res.net_recovered:>9,.0f}")

    # Save summary artifact
    out_dir = "evaluation_results"
    os.makedirs(out_dir, exist_ok=True)
    summary_path = os.path.join(out_dir, f"{manifest.experiment_id}_summary.json")
    with open(summary_path, "w") as f:
        json.dump(
            {
                "manifest": manifest.to_dict(),
                "metrics": {k: m.__dict__ for k, m in metrics.items()},
                "bootstraps": {k: b.__dict__ for k, b in bootstraps.items()},
                "attribution": {
                    "primary_window": attribution.primary_window_hours,
                    "windows": attribution.windows_evaluated,
                    "consistent": attribution.rankings_consistent,
                    "notes": attribution.notes,
                },
            },
            f,
            indent=2,
        )
    print(f"\n[Artifact Saved] Summary exported to {summary_path}\n")

if __name__ == "__main__":
    main()
