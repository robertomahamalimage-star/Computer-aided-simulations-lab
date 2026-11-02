


import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import platform
import tempfile

import numpy as np
import pandas as pd
import scipy

from stationary_analysis import StudyConfig, run_study, validate_mm1_coverage


def study_configs(replications=20, pilots=3, max_pilot_hours=96):
    base = StudyConfig(replications=replications, pilots=pilots, max_pilot_hours=max_pilot_hours)
    return [base,
            replace(base, name="fewer_taxis", fleet_size=12),
            replace(base, name="higher_demand", demand_multiplier=2),
            replace(base, name="longer_measurement", measurement_hours=48),
            replace(base, name="shorter_detector_window", window=6),
            replace(base, name="overload", fleet_size=4, demand_multiplier=4)]


def make_plots(summary, coverage, output):
    # Use a writable temporary matplotlib cache in cloud/Colab environments.
    with tempfile.TemporaryDirectory(prefix="taxi-mpl-") as cache:
        os.environ.setdefault("MPLCONFIGDIR", cache)
        os.environ.setdefault("XDG_CACHE_HOME", cache)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(17, 5), layout="constrained")
        good = summary[summary.status.eq("ok")]
        waiting = good[good.metric.eq("mean_app_wait_min")]
        for scenario, rows in waiting.groupby("scenario", sort=False):
            axes[0].plot(rows.n, rows.half_width, marker="o", label=scenario)
        axes[0].set(xlabel="Independent replicates", ylabel="Semi-amplitude IC 95% (min)",
                    title="App wait time estimation accuracy")
        if len(waiting):
            axes[0].legend(fontsize=7)
            largest = waiting.loc[waiting.groupby("scenario").n.idxmax()]
            y = np.arange(len(largest))
            axes[1].errorbar(largest.estimate, y, xerr=largest.half_width, fmt="o", capsize=4)
            axes[1].set_yticks(y, largest.scenario, fontsize=8)
        axes[1].set(xlabel="App wait time: estimate and 95% CI (min)", title="Parameter effects")
        c = coverage.iloc[0]
        axes[2].errorbar([c.empirical_coverage], [0],
                        xerr=[[c.empirical_coverage-c.coverage_wilson_lower],
                              [c.coverage_wilson_upper-c.empirical_coverage]], fmt="o", capsize=5)
        axes[2].axvline(0.95, color="gray", linestyle="--", label="95% nominal coverage")
        axes[2].set(xlim=(0.85, 1), yticks=[], xlabel="M/M/1 empirical coverage",
                    title=f"Verification on {int(c.trials)} experiments")
        axes[2].legend(fontsize=8)
        fig.savefig(output / "precision.png", dpi=160)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="stationary_results")
    parser.add_argument("--replications", type=int, default=20)
    parser.add_argument("--pilots", type=int, default=3)
    parser.add_argument("--pilot-hours", type=float, default=96)
    parser.add_argument("--coverage-trials", type=int, default=300)
    choices = [c.name for c in study_configs()]
    parser.add_argument("--scenarios", nargs="+", choices=choices, default=choices)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    configs = [c for c in study_configs(args.replications, args.pilots, args.pilot_hours)
               if c.name in args.scenarios]
    collected = [[], [], [], []]
    for config in configs:
        print(f"{config.name}: piloti e {config.replications} repliche pianificate...", flush=True)
        results = run_study(config)
        for destination, frame in zip(collected, results):
            destination.append(frame)
        print(f"  stati: {results[0].status.unique().tolist()}", flush=True)
    names = ["confidence_intervals.csv", "replications.csv", "pilots.csv", "detector_trace.csv"]
    frames = []
    for name, parts in zip(names, collected):
        nonempty = [p for p in parts if not p.empty]
        # Some failure records intentionally contain no estimates. Constructing
        # from records also handles their all-missing columns consistently.
        frame = pd.DataFrame.from_records(
            [record for part in nonempty for record in part.to_dict("records")]
        )
        if frame.empty:
            # A failed pilot produces no production data, but its CSV must
            # still have a readable header rather than being an empty file.
            empty_columns = {
                "replications.csv": ["scenario", "replication", "seed", "status",
                                     "deletion_minutes", "cohort_size", "unresolved",
                                     "mean_app_wait_min", "mean_access_min", "mean_walk_min",
                                     "occupied_share", "idle_share", "followup_used_minutes"],
                "detector_trace.csv": ["scenario", "pilot", "time_min", "stable",
                                       "mean_ratio", "drift_ratio", "detected_at_min",
                                       "pending_mean", "occupied_mean", "pending_age_mean"],
            }
            frame = pd.DataFrame(columns=empty_columns[name])
        frame.to_csv(output / name, index=False)
        frames.append(frame)
    # Keep plotting valid even if no pilot detects stability.
    summary = frames[0]
    if "metric" not in summary:
        summary["metric"] = ""
    coverage = validate_mm1_coverage(trials=args.coverage_trials)
    coverage.to_csv(output / "coverage_validation.csv", index=False)
    make_plots(summary, coverage, output)
    metadata = dict(configurations=[asdict(c) for c in configs], python=platform.python_version(),
                    numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__,
                    coverage_trials=args.coverage_trials)
    (output / "configuration.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Risultati e grafico salvati in {output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
