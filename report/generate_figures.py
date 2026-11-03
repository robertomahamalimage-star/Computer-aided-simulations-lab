"""Rebuild the report's vector figures from its archived numerical results.

Run: python3 report/generate_figures.py (NumPy, pandas, matplotlib required).
No simulations or statistical methods are changed by this script.
"""
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGURES = HERE / "figures"
FIGURES.mkdir(exist_ok=True)


def main():
    with tempfile.TemporaryDirectory(prefix="taxi-report-mpl-") as cache:
        os.environ.setdefault("MPLCONFIGDIR", cache)
        os.environ.setdefault("XDG_CACHE_HOME", cache)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import ScalarFormatter
        plt.rcParams.update({
            "font.family": "serif", "font.size": 8,
            "axes.labelsize": 8, "axes.titlesize": 8.5,
            "legend.fontsize": 7, "xtick.labelsize": 7,
            "ytick.labelsize": 7.5, "axes.spines.top": False,
            "axes.spines.right": False, "pdf.fonttype": 42,
        })
        runs = pd.read_csv(DATA / "lab1_replications.csv")
        labels = ["Baseline", "No hubs", "Rain: demand", "Rain: full",
                  "Strike", "Evening event", "Combined stress"]
        grouped = runs.groupby("scenario", sort=False)
        means, sd = grouped.mean(numeric_only=True), grouped.std(numeric_only=True, ddof=1)
        y = np.arange(len(means))
        fig, ax = plt.subplots(figsize=(3.45, 2.85), layout="constrained")
        for metric, shift, marker, color, label in [
            ("avg_app_wait_min", -.14, "o", "#23669a", "App waiting"),
            ("avg_stand_wait_min", .14, "s", "#bf6b22", "Stand queueing"),
        ]:
            ax.errorbar(means[metric], y+shift, xerr=sd[metric], fmt=marker,
                        color=color, markersize=3.5, capsize=2, lw=1, label=label)
        ax.set_yticks(y, labels)
        ax.invert_yaxis()
        ax.set_xscale("log")
        ax.set_xlim(1, 220)
        ax.set_xticks([1, 5, 10, 20, 50, 100, 200])
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.set_xlabel("Waiting time (min; logarithmic scale)")
        ax.grid(axis="x", alpha=.18)
        ax.legend(loc="lower center", bbox_to_anchor=(.5, 1.0), ncol=2,
                  frameon=False, borderaxespad=.2)
        fig.savefig(FIGURES / "lab1_waiting.pdf")
        plt.close(fig)

        trace = pd.read_csv(DATA / "lab2_detector_trace.csv")
        fig, axes = plt.subplots(2, 1, figsize=(3.45, 2.9), layout="constrained")
        for ax, scenario, title, color in zip(
            axes, ["baseline", "overload"],
            ["(a) Baseline: decision at 13 h", "(b) Overload: no decision by 96 h"],
            ["#23669a", "#a33838"],
        ):
            part = trace[(trace.scenario == scenario) & (trace.pilot == 0)]
            ax.plot(part.time_min/60, part.pending_mean, lw=1.1, color=color)
            ax.set_title(title, loc="left", pad=3)
            ax.set_ylabel("Pending users")
            ax.grid(alpha=.18)
            ax.set_xlim(0, 14 if scenario == "baseline" else 96)
            if scenario == "baseline":
                ax.axvline(13, color="#555555", linestyle="--", lw=.8)
            else:
                ax.ticklabel_format(axis="y", style="sci", scilimits=(3, 3))
            ax.set_xlabel("Simulated time (h)")
        fig.savefig(FIGURES / "warmup_traces.pdf")
        plt.close(fig)

        intervals = pd.read_csv(DATA / "lab2_intervals.csv")
        waiting = intervals[(intervals.status == "ok") & (intervals.metric == "mean_app_wait_min")]
        colors = ["#23669a", "#bf6b22", "#377d51", "#8b4f9d", "#ae3f50"]
        names = ["Baseline", "12 taxis", "Double demand", "48 h measurement", "6-batch window"]
        fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.35), layout="constrained")
        last = waiting[waiting.n == 20]
        y = np.arange(len(last))
        for index, (name, color) in enumerate(zip(last.scenario, colors)):
            row = last[last.scenario == name].iloc[0]
            axes[0].errorbar(row.estimate, index, xerr=row.half_width, fmt="o",
                             color=color, capsize=3, lw=1.1, markersize=4)
        axes[0].set_yticks(y, names)
        axes[0].invert_yaxis()
        axes[0].set_xlabel("App waiting time: mean and 95% CI (min)")
        axes[0].set_title("(a) Independent-replication estimates (R = 20)", loc="left")
        for (scenario, rows), label, color in zip(waiting.groupby("scenario", sort=False), names, colors):
            rows = rows.sort_values("n")
            axes[1].plot(rows.n, rows.half_width, "o-", color=color, lw=1,
                         markersize=3.5, label=label)
        axes[1].set_xticks([10, 20])
        axes[1].set_xlim(8.5, 21.5)
        axes[1].set_ylim(0, 2.3)
        axes[1].set_xlabel("Independent replications, R")
        axes[1].set_ylabel("95% CI half-width (min)")
        axes[1].set_title("(b) Observed precision", loc="left")
        axes[1].legend(frameon=False, loc="center right", bbox_to_anchor=(1, .45),
                       ncol=2, fontsize=6.8, columnspacing=.7, handlelength=1.4)
        for ax in axes:
            ax.grid(alpha=.18)
        fig.savefig(FIGURES / "precision_comparison.pdf")
        plt.close(fig)


if __name__ == "__main__":
    main()
