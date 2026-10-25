"""Second lab: run pilot warm-up detection, independent CIs and precision study.

Usage: python3 taxi_stationary_lab.py
Colab: clone/download this file, stationary_analysis.py and taxi_simulation_v3.py.
"""

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
        axes[0].set(xlabel="Repliche indipendenti", ylabel="Semiampiezza IC 95% (min)",
                    title="Precisione della stima dell'attesa app")
        if len(waiting):
            axes[0].legend(fontsize=7)
            largest = waiting.loc[waiting.groupby("scenario").n.idxmax()]
            y = np.arange(len(largest))
            axes[1].errorbar(largest.estimate, y, xerr=largest.half_width, fmt="o", capsize=4)
            axes[1].set_yticks(y, largest.scenario, fontsize=8)
        axes[1].set(xlabel="Attesa app: stima e IC 95% (min)", title="Effetto dei parametri")
        c = coverage.iloc[0]
        axes[2].errorbar([c.empirical_coverage], [0],
                        xerr=[[c.empirical_coverage-c.coverage_wilson_lower],
                              [c.coverage_wilson_upper-c.empirical_coverage]], fmt="o", capsize=5)
        axes[2].axvline(0.95, color="gray", linestyle="--", label="Copertura nominale 95%")
        axes[2].set(xlim=(0.85, 1), yticks=[], xlabel="Copertura empirica M/M/1",
                    title=f"Verifica su {int(c.trials)} esperimenti")
        axes[2].legend(fontsize=8)
        fig.savefig(output / "precision.png", dpi=160)
        plt.close(fig)


def write_report(summary, pilots, coverage, output):
    lines = [
        "# Laboratorio: transitorio e intervalli di confidenza", "",
        "Risultati riproducibili dello studio a domanda e velocità costanti. "
        "Gli scenari giornalieri del primo laboratorio restano separati.", "",
        "I piloti scelgono il tempo da scartare; le repliche di misura usano stream "
        "indipendenti dai piloti. Gli IC sono Student-t tra medie di replica. "
        "La stabilità rilevata è un controllo euristico, non una prova matematica. "
        "Gli IC hanno copertura nominale, non una garanzia sul sistema taxi.", "",
        "| Scenario | Piloti con rilevamento | Scarto (ore) | Repliche | Attesa app (min) | IC 95% (min) | Semiampiezza relativa |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for name, rows in summary.groupby("scenario", sort=False):
        p = pilots[pilots.scenario.eq(name)]
        successes = int(p.status.eq("detected").sum())
        good = rows[rows.status.eq("ok") & rows.metric.eq("mean_app_wait_min")]
        if good.empty:
            lines.append(f"| {name} | {successes}/{len(p)} | — | — | — | {rows.iloc[-1].status} | — |")
            continue
        best = good.loc[good.n.idxmax()]
        lines.append(f"| {name} | {successes}/{len(p)} | {best.deletion_minutes/60:.1f} | "
                     f"{int(best.n)} | {best.estimate:.3f} | [{best.lower:.3f}, {best.upper:.3f}] | "
                     f"{100*best.relative_half_width:.1f}% |")
    lines += ["", "## Impatto sulla precisione", "",
              "Per ciascuna configurazione il piano confronta due numerosità fissate "
              "prima della misura. La semiampiezza descrive la precisione; "
              "non misura direttamente il bias residuo del transitorio.", ""]
    for name, rows in summary.groupby("scenario", sort=False):
        good = rows[rows.status.eq("ok") & rows.metric.eq("mean_app_wait_min")].sort_values("n")
        if len(good) == 2:
            a, b = good.iloc[0], good.iloc[1]
            lines.append(f"- {name}: passando da {int(a.n)} a {int(b.n)} repliche, "
                         f"la semiampiezza passa da {a.half_width:.3f} a {b.half_width:.3f} minuti.")
    lines += ["", "Il caso `longer_measurement` raddoppia la durata utile da 24 a 48 ore; "
              "`shorter_detector_window` dimezza la finestra da 12 a 6 batch. "
              "Gli altri confronti modificano flotta e carico. Per confrontare "
              "l'accuratezza guardare gli IC, lo scarto e le mancate rilevazioni "
              "insieme: un intervallo stretto da solo non esclude un bias.", "",
              "I confronti di numerosità condividono il prefisso delle stesse repliche, "
              "ma non effettuano arresto adattivo. Gli IC riportati sono marginali, "
              "non simultanei su tutti i parametri e non IC delle differenze.", ""]
    c = coverage.iloc[0]
    lines += ["## Verifica con un riferimento noto", "",
              f"Su {int(c.trials)} esperimenti M/M/1, ciascuno con {int(c.replications)} "
              f"repliche e {int(c.customers_per_replication)} clienti per replica, "
              f"la copertura osservata è {100*c.empirical_coverage:.1f}% "
              f"(nominale 95%; intervallo Wilson sulla copertura "
              f"[{100*c.coverage_wilson_lower:.1f}%, {100*c.coverage_wilson_upper:.1f}%]). "
              f"L'attesa media teorica è 1; la stima media è {c.mean_estimate:.4f}.", "",
              "Questa verifica usa attese correlate dentro ogni replica e una "
              "distribuzione iniziale esattamente stazionaria. Controlla il metodo "
              "degli IC su una coda nota; non certifica il rilevatore del transitorio "
              "o la copertura degli IC taxi.", "",
              "## Limiti e file", "",
              "- `warmup_not_detected`: almeno un pilota non supera il controllo "
              "entro l'orizzonte massimo. Non equivale da solo a una prova di instabilità.",
              "- `incomplete_measurements`: almeno una replica del campione ha "
              "clienti non ancora saliti a fine follow-up o una popolazione vuota. "
              "Non si eliminano repliche fallite per ottenere un IC.",
              "- La produzione mantiene gli arrivi durante il follow-up della "
              "coorte; le quote di utilizzo rimangono riferite alla sola finestra utile.",
              "- Le soglie del rilevatore sono configurabili e non garantiscono "
              "l'assenza di transitori lenti. Aumentare durata e finestre serve come controllo di sensibilità.",
              "- Per istruzioni e formule vedere `README_STATIONARY.md`.", "",
              "![Precisione e copertura](precision.png)", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


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
    # If every configuration fails its pilot, still export a truthful report.
    summary = frames[0]
    if "metric" not in summary:
        summary["metric"] = ""
    coverage = validate_mm1_coverage(trials=args.coverage_trials)
    coverage.to_csv(output / "coverage_validation.csv", index=False)
    make_plots(summary, coverage, output)
    write_report(summary, frames[2], coverage, output)
    metadata = dict(configurations=[asdict(c) for c in configs], python=platform.python_version(),
                    numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__,
                    coverage_trials=args.coverage_trials)
    (output / "configuration.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Risultati, grafico e relazione salvati in {output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
