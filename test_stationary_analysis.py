"""Known-answer and end-to-end checks for the second laboratory."""

import unittest
from unittest.mock import patch

import numpy as np

from stationary_analysis import (
    OnlineWarmupDetector, StudyConfig, pilot_run, production_run, run_study,
    student_interval, validate_mm1_coverage,
)
from taxi_simulation_v3 import Passenger, TaxiSimulation


class StationaryModeTests(unittest.TestCase):
    def test_inputs_do_not_depend_on_clock_or_day(self):
        sim = TaxiSimulation(stationary=True, include_hubs=False, rebalancing=False,
                             weather_intensity=0.5, public_transport_availability=0.8)
        times = [0, 8*60, 18*60, 24*60, 100*60]
        rates = [sim.zone_rate_per_hour(sim.zones[0], time) for time in times]
        speeds = [sim.taxi_speed_at(time, np.array([2., 8.])) for time in times]
        np.testing.assert_allclose(rates, rates[0])
        np.testing.assert_allclose(speeds, speeds[0])

    def test_dynamic_settings_must_be_explicitly_disabled(self):
        options = dict(stationary=True, include_hubs=False, rebalancing=False)
        for changes in ({"include_hubs": True}, {"rebalancing": True},
                        {"event_zone": "NE"}, {"strike": True}, {"day_of_week": "Friday"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                TaxiSimulation(**(options | changes))


class DetectorTests(unittest.TestCase):
    def test_declining_transient_followed_by_constant_signal(self):
        detector = OnlineWarmupDetector(window=4, consecutive=2, tolerance=0.1,
                                       absolute_tolerances=(0.01,))
        observations = np.r_[np.linspace(50, 10, 20), np.full(30, 2.0)]
        for index, value in enumerate(observations, start=1):
            detector.update(index, [value])
            if index <= 20:
                self.assertIsNone(detector.detected_at)
        self.assertIsNotNone(detector.detected_at)
        self.assertGreater(detector.detected_at, 20)
        self.assertLessEqual(len(detector.values), 8)

    def test_growing_queue_is_not_declared_stable(self):
        detector = OnlineWarmupDetector(window=6, absolute_tolerances=(0.1,))
        for index in range(1, 301):
            detector.update(index, [index])
        self.assertIsNone(detector.detected_at)

    def test_constant_input_requires_two_windows_and_confirmation(self):
        detector = OnlineWarmupDetector(window=4, consecutive=3, absolute_tolerances=(0.1,))
        for index in range(1, 10):
            detector.update(index, [3])
            self.assertIsNone(detector.detected_at)
        detector.update(10, [3])
        self.assertEqual(detector.detected_at, 10)

    def test_stationary_noise_is_detected(self):
        detector = OnlineWarmupDetector(window=12, absolute_tolerances=(0.1,))
        rng = np.random.default_rng(52)
        for index, value in enumerate(rng.normal(size=300), start=1):
            detector.update(index, [value])
        self.assertIsNotNone(detector.detected_at)

    def test_invalid_observations_do_not_silently_pass(self):
        detector = OnlineWarmupDetector(absolute_tolerances=(1,))
        with self.assertRaises(ValueError):
            detector.update(1, [np.nan])
        detector.update(1, [0])
        with self.assertRaises(ValueError):
            detector.update(1, [0])
        with self.assertRaises(ValueError):
            detector.update(2, [0, 1])


class ConfidenceIntervalTests(unittest.TestCase):
    def test_known_student_t_interval(self):
        interval = student_interval([1, 2, 3, 4, 5])
        self.assertEqual(interval["estimate"], 3)
        self.assertAlmostEqual(interval["lower"], 1.0367568385)
        self.assertAlmostEqual(interval["upper"], 4.9632431615)

    def test_more_confidence_means_wider_interval(self):
        a = student_interval([1, 2, 3, 4, 5], 0.95)
        b = student_interval([1, 2, 3, 4, 5], 0.99)
        self.assertGreater(b["half_width"], a["half_width"])

    def test_missing_replications_are_rejected(self):
        for values in ([1], [1, np.nan], [1, np.inf], [[1, 2]]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                student_interval(values)

    def test_mm1_reference_has_correct_mean_and_plausible_coverage(self):
        result = validate_mm1_coverage(trials=100, replications=20, customers=1000).iloc[0]
        self.assertAlmostEqual(result.mean_estimate, 1, delta=0.05)
        self.assertLessEqual(result.coverage_wilson_lower, 0.95)
        self.assertGreaterEqual(result.coverage_wilson_upper, 0.95)


class MeasurementTests(unittest.TestCase):
    @staticmethod
    def controlled_sim(duration_hours):
        sim = TaxiSimulation(stationary=True, include_hubs=False, rebalancing=False,
                             fleet_size=1, demand_multiplier=0, duration_hours=duration_hours,
                             road_distance_factor=1)
        calls = []

        def arrivals():
            calls.append(sim.current_time)
            # A customer arriving during the measurement window [1, 2).
            if sim.current_time == 1:
                origin = sim.stands[0].pos + [2, 0]
                sim._register_passenger(Passenger(
                    pid=sim.next_pid, origin=origin, destination=origin+[1, 0],
                    origin_zone="NW", destination_zone="NW", mode="app", request_time=1,
                ))

        sim.generate_urban_passengers = arrivals
        sim.taxi_speed_at = lambda minute, pos: 60
        return sim, calls

    def test_cohort_followup_and_utilization_have_different_endpoints(self):
        config = StudyConfig(measurement_hours=1/60, followup_hours=2/60)
        sim, calls = self.controlled_sim(4/60)
        with patch("stationary_analysis.make_stationary_sim", return_value=sim):
            row = production_run(config, seed=1, deletion_minutes=1)
        self.assertEqual(row["status"], "complete")
        self.assertEqual(row["cohort_size"], 1)
        self.assertEqual(row["mean_app_wait_min"], 2)
        self.assertEqual(row["followup_used_minutes"], 1)
        self.assertEqual(row["occupied_share"], 0)
        self.assertIn(2, calls)  # Arrival generation continued after measurement.

    def test_timeout_does_not_drop_waiting_customer(self):
        config = StudyConfig(measurement_hours=1/60, followup_hours=1/60)
        sim, _ = self.controlled_sim(3/60)
        sim.taxi_speed_at = lambda minute, pos: 0.01
        with patch("stationary_analysis.make_stationary_sim", return_value=sim):
            row = production_run(config, seed=1, deletion_minutes=1)
        self.assertEqual(row["status"], "incomplete_cohort")
        self.assertEqual(row["unresolved"], 1)
        self.assertTrue(np.isnan(row["mean_app_wait_min"]))

    def test_pilots_and_production_are_independent_and_share_fixed_cutoff(self):
        config = StudyConfig(replications=4, pilots=3)
        pilot_seeds, production_seeds, cutoffs = [], [], []

        def pilot(c, seed):
            pilot_seeds.append(seed)
            return (600 + 30*len(pilot_seeds)), []

        def production(c, seed, cutoff):
            production_seeds.append(seed)
            cutoffs.append(cutoff)
            return dict(status="complete", mean_app_wait_min=5, mean_access_min=10,
                        mean_walk_min=3, occupied_share=0.3, idle_share=0.4)

        with patch("stationary_analysis.pilot_run", side_effect=pilot), \
             patch("stationary_analysis.production_run", side_effect=production):
            summary, replications, _, _ = run_study(config)
        self.assertEqual(set(cutoffs), {690})
        self.assertFalse(set(pilot_seeds) & set(production_seeds))
        self.assertEqual(len(set(production_seeds)), 4)
        self.assertEqual(len(replications), 4)
        self.assertEqual(set(summary.n), {2, 4})

    def test_failed_pilot_blocks_production(self):
        with patch("stationary_analysis.pilot_run", return_value=(None, [])), \
             patch("stationary_analysis.production_run") as production:
            summary, replications, _, _ = run_study(StudyConfig(replications=4))
        production.assert_not_called()
        self.assertEqual(summary.iloc[0].status, "warmup_not_detected")
        self.assertTrue(replications.empty)

    def test_failed_replication_is_not_removed_from_interval(self):
        def production(c, seed, cutoff):
            return dict(status="incomplete_cohort", mean_app_wait_min=np.nan,
                        mean_access_min=np.nan, mean_walk_min=np.nan,
                        occupied_share=0.3, idle_share=0.4)
        with patch("stationary_analysis.pilot_run", return_value=(600, [])), \
             patch("stationary_analysis.production_run", side_effect=production):
            summary, _, _, _ = run_study(StudyConfig(replications=4))
        self.assertTrue(summary.status.eq("incomplete_measurements").all())
        self.assertNotIn("lower", summary)

    def test_real_taxi_pilot_and_independent_production(self):
        config = StudyConfig(replications=2, pilots=1, max_pilot_hours=48,
                             measurement_hours=2, followup_hours=24)
        summary, replications, pilots, trace = run_study(config)
        self.assertEqual(pilots.iloc[0].status, "detected")
        self.assertTrue(summary.status.eq("ok").all())
        self.assertTrue(replications.unresolved.eq(0).all())
        self.assertEqual(len(replications), 2)
        self.assertGreater(len(trace), 2*config.window)


if __name__ == "__main__":
    unittest.main()
