"""Online warm-up screening and fixed-design, independent-replication inference.

The detector is a practical stability heuristic, not a proof of stationarity.
Pilot streams select deletion time; independent production streams estimate KPIs.
We never treat autocorrelated minute-by-minute observations as IID samples.
"""

from collections import deque
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy.stats import binomtest, t

from taxi_simulation_v3 import TaxiSimulation


class OnlineWarmupDetector:
    """Compare two adjacent windows of *non-overlapping batch averages* online.

    Check both mean displacement and fitted linear drift, for every monitored
    state variable. A practical tolerance is absolute_tolerance + tolerance *
    window SD. Multiple consecutive passes are required. The absolute part is
    in each variable's units; it is not a significance level. Memory is bounded
    by two windows and only data available at update time are examined.

    Apparent stability over finite windows can miss slow transients or a later
    change. No automated finite-data rule can guarantee a steady state exists.
    """

    def __init__(self, window=12, consecutive=3, tolerance=0.5,
                 absolute_tolerances=(1.5, 0.05, 5.0)):
        if not isinstance(window, int) or window < 4:
            raise ValueError("window must be an integer >= 4")
        if not isinstance(consecutive, int) or consecutive < 1:
            raise ValueError("consecutive must be a positive integer")
        floors = np.asarray(absolute_tolerances, dtype=float)
        if floors.ndim != 1 or not len(floors) or not np.isfinite(floors).all() or (floors <= 0).any():
            raise ValueError("absolute tolerances must be finite and positive")
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("tolerance must be finite and positive")
        self.window = window
        self.consecutive = consecutive
        self.tolerance = tolerance
        self.floors = floors
        self.values = deque(maxlen=2 * window)
        self.streak = 0
        self.detected_at = None
        self.last_time = -math.inf

    def update(self, time_minutes, observation):
        values = np.asarray(observation, dtype=float)
        if values.shape != self.floors.shape or not np.isfinite(values).all():
            raise ValueError("observation must match tolerances and be finite")
        if not math.isfinite(time_minutes) or time_minutes <= self.last_time:
            raise ValueError("observation times must be finite and increasing")
        self.last_time = time_minutes
        self.values.append(values)
        result = dict(time_min=time_minutes, stable=False, mean_ratio=np.nan,
                      drift_ratio=np.nan, detected_at_min=self.detected_at)
        if len(self.values) < 2 * self.window:
            return result
        data = np.asarray(self.values)
        scale = self.floors + self.tolerance * data.std(axis=0, ddof=1)
        displacement = np.abs(data[:self.window].mean(axis=0) - data[self.window:].mean(axis=0))
        x = np.arange(len(data), dtype=float)
        x -= x.mean()
        # Express fitted slope as change across the whole two-window span.
        drift = np.abs(x @ data / (x @ x)) * (len(data) - 1)
        mean_ratio = float(np.max(displacement / scale))
        drift_ratio = float(np.max(drift / (2 * scale)))
        stable = mean_ratio <= 1 and drift_ratio <= 1
        self.streak = self.streak + 1 if stable else 0
        if self.detected_at is None and self.streak >= self.consecutive:
            self.detected_at = time_minutes
        result.update(stable=stable, mean_ratio=mean_ratio, drift_ratio=drift_ratio,
                      detected_at_min=self.detected_at)
        return result


def student_interval(replication_means, confidence=0.95):
    """Two-sided Student-t interval across independent *replication means*.

    Missing/failed replications are rejected, not silently filtered. The number
    of replications and observation horizon must be fixed before looking at the
    production data. Approximate coverage still requires negligible initial
    bias and sufficiently well behaved replication averages.
    """
    values = np.asarray(replication_means, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("need at least two finite independent replication means")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    se = sd / math.sqrt(len(values))
    half = float(t.ppf((1 + confidence) / 2, df=len(values) - 1) * se)
    return dict(n=len(values), confidence=confidence, estimate=mean, sample_sd=sd,
                standard_error=se, half_width=half, lower=mean-half, upper=mean+half,
                relative_half_width=half / abs(mean) if mean != 0 else np.nan)


@dataclass(frozen=True)
class StudyConfig:
    name: str = "baseline"
    fleet_size: int = 20
    demand_multiplier: float = 1.0
    measurement_hours: float = 24
    replications: int = 20
    pilots: int = 3
    max_pilot_hours: float = 96
    followup_hours: float = 48
    batch_minutes: int = 30
    window: int = 12
    consecutive: int = 3
    tolerance: float = 0.5
    confidence: float = 0.95
    seed: int = 20261025

    def __post_init__(self):
        for name in ("measurement_hours", "max_pilot_hours", "followup_hours"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name, minimum in (("replications", 2), ("pilots", 1), ("batch_minutes", 1)):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if not 0 < self.confidence < 1:
            raise ValueError("confidence must be in (0, 1)")
        OnlineWarmupDetector(self.window, self.consecutive, self.tolerance)


def make_stationary_sim(config, duration_hours, seed):
    return TaxiSimulation(
        stationary=True, include_hubs=False, rebalancing=False,
        duration_hours=duration_hours, fleet_size=config.fleet_size,
        demand_multiplier=config.demand_multiplier, seed=seed,
    )


def state_observation(sim):
    """Current state, not cumulative means that hide a growing queue.

    Monitor total not-yet-boarded customers (including walkers), occupied share
    and mean age of those customers. The last variable helps expose starvation
    even if a small stand queue has an apparently constant length.
    """
    pending = [p for p in sim.passengers.values() if p.pickup_time is None]
    age = np.mean([sim.current_time - p.request_time for p in pending]) if pending else 0.0
    occupied = sum(taxi.state == "occupied" for taxi in sim.taxis.values())
    return np.array([len(pending), occupied / sim.fleet_size if sim.fleet_size else 0, age])


def pilot_run(config, seed):
    """Feed time-weighted batch state averages to the detector while running."""
    sim = make_stationary_sim(config, config.max_pilot_hours, seed)
    detector = OnlineWarmupDetector(config.window, config.consecutive, config.tolerance)
    accumulated = np.zeros(3)
    elapsed = 0.0
    trace = []
    while sim.current_time < sim.duration_minutes:
        dt = sim.step_duration
        # Left-endpoint state samples: each gets its actual interval length.
        accumulated += state_observation(sim) * dt
        elapsed += dt
        sim.step()
        if elapsed >= config.batch_minutes - 1e-9:
            observation = accumulated / elapsed
            record = detector.update(sim.current_time, observation)
            record.update(pending_mean=observation[0], occupied_mean=observation[1],
                          pending_age_mean=observation[2])
            trace.append(record)
            accumulated[:] = 0
            elapsed = 0
            if detector.detected_at is not None:
                break
    return detector.detected_at, trace


def production_run(config, seed, deletion_minutes):
    """Measure a fixed post-deletion window; follow its arrival cohort to pickup.

    Arrivals CONTINUE normally during follow-up. Turning them off would change
    the queue seen by the last customers. Follow-up does not extend utilization
    observation. A timeout invalidates the replication rather than deleting
    the still-waiting people from an apparently successful mean.
    """
    duration = deletion_minutes / 60 + config.measurement_hours + config.followup_hours
    sim = make_stationary_sim(config, duration, seed)
    end = deletion_minutes + 60 * config.measurement_hours

    def advance_until(target):
        # Study boundaries lie on the one-minute grid; reject otherwise rather
        # than inadvertently observing a different cohort or horizon.
        if not math.isclose(target, round(target), abs_tol=1e-8):
            raise ValueError("study boundaries must lie on the one-minute grid")
        while sim.current_time < target - 1e-9:
            sim.step()

    advance_until(deletion_minutes)
    occupied_before = sum(t.occupied_minutes for t in sim.taxis.values())
    idle_before = sum(t.idle_minutes for t in sim.taxis.values())
    advance_until(end)
    occupied_delta = sum(t.occupied_minutes for t in sim.taxis.values()) - occupied_before
    idle_delta = sum(t.idle_minutes for t in sim.taxis.values()) - idle_before
    denominator = sim.fleet_size * 60 * config.measurement_hours
    cohort = [p for p in sim.passengers.values() if deletion_minutes <= p.request_time < end]
    while any(p.pickup_time is None for p in cohort) and sim.current_time < sim.duration_minutes:
        sim.step()
    unresolved = sum(p.pickup_time is None for p in cohort)
    row = dict(
        seed=seed, deletion_minutes=deletion_minutes, cohort_size=len(cohort),
        unresolved=unresolved, followup_used_minutes=sim.current_time-end,
        status="complete" if not unresolved and cohort else "incomplete_cohort",
        occupied_share=occupied_delta/denominator if denominator else np.nan,
        idle_share=idle_delta/denominator if denominator else np.nan,
        mean_app_wait_min=np.nan, mean_access_min=np.nan, mean_walk_min=np.nan,
    )
    if row["status"] == "complete":
        app = [p for p in cohort if p.mode == "app"]
        stand = [p for p in cohort if p.mode == "stand"]
        row["mean_app_wait_min"] = float(np.mean([p.pickup_time-p.request_time for p in app])) if app else np.nan
        row["mean_access_min"] = float(np.mean([p.pickup_time-p.request_time for p in cohort]))
        row["mean_walk_min"] = float(np.mean([p.stand_arrival_time-p.request_time for p in stand])) if stand else np.nan
    return row


def run_study(config):
    """Select deletion on pilots, then run the predeclared production sample.

    Reuse stream families across configurations for interpretable comparisons;
    within a configuration each replication and each pilot has a distinct stream.
    CIs below are marginal intervals, not simultaneous or paired-difference CIs.
    """
    pilot_family, production_family = np.random.SeedSequence(config.seed).spawn(2)
    pilot_seeds = [int(s.generate_state(1)[0]) for s in pilot_family.spawn(config.pilots)]
    production_seeds = [int(s.generate_state(1)[0]) for s in production_family.spawn(config.replications)]
    pilots, trace = [], []
    for index, seed in enumerate(pilot_seeds):
        detected, records = pilot_run(config, seed)
        pilots.append(dict(scenario=config.name, pilot=index, seed=seed,
                           detected_at_min=detected,
                           status="detected" if detected is not None else "not_detected"))
        trace.extend(dict(scenario=config.name, pilot=index, **record) for record in records)
    metadata = dict(scenario=config.name, fleet_size=config.fleet_size,
                    demand_multiplier=config.demand_multiplier,
                    measurement_hours=config.measurement_hours, window=config.window,
                    tolerance=config.tolerance, requested_replications=config.replications)
    summary, replications = [], []
    if any(p["detected_at_min"] is None for p in pilots):
        summary.append(dict(**metadata, status="warmup_not_detected", n=0))
    else:
        deletion = max(p["detected_at_min"] for p in pilots)
        for index, seed in enumerate(production_seeds):
            replications.append(dict(scenario=config.name, replication=index,
                                     **production_run(config, seed, deletion)))
        frame = pd.DataFrame(replications)
        # Two fixed sample sizes assess precision without optional stopping.
        sizes = sorted({max(2, config.replications // 2), config.replications})
        for size in sizes:
            subset = frame.iloc[:size]
            for metric in ("mean_app_wait_min", "mean_access_min", "mean_walk_min", "occupied_share", "idle_share"):
                record = dict(**metadata, deletion_minutes=deletion, metric=metric, n=size)
                if not subset.status.eq("complete").all() or not np.isfinite(subset[metric]).all():
                    record.update(status="incomplete_measurements")
                else:
                    record.update(student_interval(subset[metric], config.confidence), status="ok")
                summary.append(record)
    return (pd.DataFrame(summary), pd.DataFrame(replications),
            pd.DataFrame(pilots), pd.DataFrame(trace))


def validate_mm1_coverage(trials=300, replications=20, customers=3000, seed=71023):
    """Empirical CI coverage on a queue with known mean waiting time Wq=1.

    M/M/1: lambda=0.5, mu=1. Start workload in its EXACT invariant distribution
    (mass 1-rho at zero, otherwise Exp(mu-lambda)). Lindley's recurrence creates
    correlated waits within each replication; replication streams are independent.
    This checks CI calibration on a reference model, not taxi warm-up correctness.
    """
    for name, value in (("trials", trials), ("replications", replications), ("customers", customers)):
        if not isinstance(value, int) or value < 2:
            raise ValueError(f"{name} must be an integer >= 2")
    rng = np.random.default_rng(seed)
    shape = (trials, replications)
    waits = np.where(rng.random(shape) < 0.5, rng.exponential(2, shape), 0.0)
    totals = np.zeros(shape)
    for _ in range(customers):
        totals += waits
        waits = np.maximum(0, waits + rng.exponential(1, shape) - rng.exponential(2, shape))
    means = totals / customers
    estimates = means.mean(axis=1)
    half = t.ppf(0.975, replications-1) * means.std(axis=1, ddof=1) / math.sqrt(replications)
    covered = int(np.sum((estimates-half <= 1) & (estimates+half >= 1)))
    coverage_interval = binomtest(covered, trials).proportion_ci(method="wilson")
    return pd.DataFrame([dict(
        model="M/M/1", theoretical_mean_wait=1.0, trials=trials,
        replications=replications, customers_per_replication=customers,
        nominal_coverage=0.95, empirical_coverage=covered/trials,
        coverage_wilson_lower=coverage_interval.low, coverage_wilson_upper=coverage_interval.high,
        mean_estimate=float(estimates.mean()), mean_half_width=float(half.mean()),
    )])
