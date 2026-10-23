"""Regression tests for time order, observation bias and physical constraints.

Run with: python3 -B -m unittest -v
Controlled trips use known distances/speeds; the final test exercises real demand.
"""

import math
import unittest
from unittest.mock import Mock, patch

import numpy as np

from taxi_simulation_v3 import (
    Passenger,
    TaxiSimulation,
    run_replications,
    summarize_experiments,
)


def make_sim(**kwargs):
    options = dict(
        fleet_size=1, duration_hours=1, include_hubs=False,
        rebalancing=False, demand_multiplier=0,
    )
    options.update(kwargs)
    return TaxiSimulation(**options)


def add_customer(sim, mode="app", origin=None, destination=None):
    pos = sim.stands[0].pos
    p = Passenger(
        pid=sim.next_pid,
        origin=np.array(pos if origin is None else origin, dtype=float),
        destination=np.array(pos + [1, 0] if destination is None else destination, dtype=float),
        origin_zone="NW", destination_zone="NW", mode=mode,
        request_time=sim.current_time,
    )
    sim._register_passenger(p)
    return p


class TimeOrderTests(unittest.TestCase):
    def test_new_customer_at_stand_boards_at_generation_time(self):
        sim = make_sim()
        customers = []

        def generate_once():
            if sim.current_time == 0:
                customers.append(add_customer(sim, mode="stand"))

        with patch.object(sim, "generate_urban_passengers", side_effect=generate_once):
            sim.step()
        p = customers[0]
        self.assertEqual((p.request_time, p.stand_arrival_time, p.pickup_time), (0, 0, 0))
        self.assertGreater(sim.taxis[0].occupied_minutes, 0)

    def test_one_minute_walk_has_no_extra_step(self):
        sim = make_sim(walking_speed_kmh=7.5)
        p = add_customer(sim, mode="stand", origin=sim.stands[0].pos + [0.125, 0])
        sim.step()
        self.assertEqual(p.stand_arrival_time, 1)
        self.assertEqual(p.pickup_time, 1)
        # Boarding at t=1 cannot cause movement during [0, 1).
        self.assertEqual(sim.taxis[0].occupied_minutes, 0)
        np.testing.assert_array_equal(sim.taxis[0].pos, sim.stands[0].pos)

    def test_taxi_cannot_be_dispatched_before_returning(self):
        sim = make_sim()
        taxi = sim.taxis[0]
        taxi.state = "returning"
        taxi.stand_id = None
        taxi.target_stand_id = 0
        taxi.target_pos = sim.stands[0].pos.copy()
        taxi.pos = taxi.target_pos - [0.1, 0]
        p = add_customer(sim)
        sim.step()
        self.assertIsNone(p.assignment_time)
        self.assertEqual(taxi.state, "idle")
        sim.step()
        self.assertEqual(p.assignment_time, 1)
        self.assertEqual(p.pickup_time, 1)
        self.assertEqual(sim.immediate_app_dispatches, 0)

    def test_known_pickup_and_ride_distances(self):
        sim = make_sim(duration_hours=2 / 60, road_distance_factor=1)
        origin = sim.stands[0].pos + [1, 0]
        p = add_customer(sim, origin=origin, destination=origin + [1, 0])
        with patch.object(sim, "taxi_speed_at", return_value=60):
            metrics = sim.run()
        self.assertEqual((p.assignment_time, p.pickup_time, p.dropoff_time), (0, 1, 2))
        self.assertEqual(p.status, "completed")
        self.assertAlmostEqual(metrics["avg_app_wait_min"], 1)
        self.assertAlmostEqual(sim.taxis[0].pickup_km, 1)
        self.assertAlmostEqual(sim.taxis[0].occupied_km, 1)

    def test_zero_distance_app_pickup_is_immediate(self):
        sim = make_sim()
        p = add_customer(sim)
        sim.dispatch_app_queue()
        self.assertEqual(p.pickup_time, 0)
        self.assertEqual(p.status, "onboard")

    def test_trip_ending_at_stand_does_not_need_return_step(self):
        sim = make_sim(duration_hours=2 / 60, road_distance_factor=1)
        stand_pos = sim.stands[0].pos.copy()
        p = add_customer(sim, origin=stand_pos + [1, 0], destination=stand_pos)
        with patch.object(sim, "taxi_speed_at", return_value=60):
            sim.run()
        self.assertEqual(p.dropoff_time, 2)
        self.assertEqual(sim.taxis[0].state, "idle")
        self.assertEqual(sim.taxis[0].stand_id, 0)
        self.assertEqual(sim.taxis[0].return_minutes, 0)

    def test_waiting_passenger_gets_arriving_taxi(self):
        sim = make_sim()
        taxi = sim.taxis[0]
        taxi.state = "returning"
        taxi.stand_id = None
        taxi.target_stand_id = 0
        taxi.target_pos = sim.stands[0].pos.copy()
        taxi.pos = taxi.target_pos - [0.1, 0]
        p = add_customer(sim, mode="stand")
        self.assertEqual(p.stand_arrival_time, 0)
        sim.step()
        self.assertEqual(p.pickup_time, 1)
        self.assertEqual(taxi.occupied_minutes, 0)


class ObservationTests(unittest.TestCase):
    def test_app_metrics_include_onboard_and_show_unserved_customers(self):
        # Build an observation with one completed, one onboard and one waiting.
        sim = make_sim(fleet_size=0)
        completed = add_customer(sim)
        completed.pickup_time, completed.dropoff_time, completed.status = 5, 10, "completed"
        onboard = add_customer(sim)
        onboard.pickup_time, onboard.status = 15, "onboard"
        add_customer(sim)
        sim.current_time = 20
        metrics = sim.metrics()
        self.assertEqual(metrics["avg_app_wait_min"], 10)
        self.assertAlmostEqual(metrics["avg_app_wait_lower_bound_min"], 40 / 3)
        self.assertEqual(metrics["boarded_app"], 2)
        self.assertEqual(metrics["not_boarded_app"], 1)
        self.assertEqual(metrics["onboard"], 1)
        self.assertEqual(metrics["unfinished_app"], 2)
        self.assertEqual(metrics["completed"] + metrics["unfinished_app"], metrics["generated"])

    def test_walk_metrics_include_people_waiting_at_stand(self):
        sim = make_sim(fleet_size=0)
        people = [add_customer(sim, mode="stand", origin=[0, 10]) for _ in range(3)]
        people[0].stand_arrival_time = 3
        people[0].pickup_time, people[0].status = 5, "onboard"
        people[1].stand_arrival_time, people[1].status = 7, "waiting_stand"
        sim.current_time = 20
        metrics = sim.metrics()
        self.assertEqual(metrics["avg_stand_walk_min"], 5)
        self.assertEqual(metrics["avg_stand_wait_min"], 2)
        self.assertEqual(metrics["avg_stand_walk_lower_bound_min"], 10)
        self.assertEqual(metrics["avg_stand_wait_lower_bound_min"], 7.5)
        self.assertEqual(metrics["walking_to_stand"], 1)
        self.assertEqual(metrics["waiting_at_stand"], 1)
        self.assertEqual(metrics["not_boarded_stand"], 2)
        self.assertEqual(metrics["unfinished_stand"], 3)

    def test_no_customers_yields_undefined_wait_not_zero(self):
        metrics = make_sim().run()
        self.assertEqual(metrics["generated"], 0)
        self.assertTrue(math.isnan(metrics["avg_app_wait_min"]))
        self.assertTrue(math.isnan(metrics["avg_app_wait_lower_bound_min"]))
        self.assertEqual(metrics["availability_idle_share"], 1)

    def test_intermediate_utilization_uses_elapsed_time(self):
        sim = make_sim()
        sim.step()
        self.assertEqual(sim.metrics()["availability_idle_share"], 1)


class ConfigurationTests(unittest.TestCase):
    def test_last_interval_ends_exactly_at_horizon(self):
        sim = make_sim(dt_minutes=7)
        metrics = sim.run()
        self.assertEqual(sim.current_time, 60)
        self.assertEqual(sim.dt, 7)
        self.assertEqual(sim.taxis[0].idle_minutes, 60)
        self.assertEqual(metrics["availability_idle_share"], 1)
        sim.step()
        self.assertEqual(sim.current_time, 60)

    def test_last_interval_demand_uses_shortened_duration(self):
        sim = make_sim(duration_hours=1 / 60, dt_minutes=7, demand_multiplier=1)
        with patch.object(sim, "rng", Mock()) as rng:
            rng.poisson.return_value = 0
            sim.run()
            mean_total = sum(call.args[0] for call in rng.poisson.call_args_list)
        # Four zones: 20 passengers/hour, multiplied by 0.35 at midnight.
        self.assertAlmostEqual(mean_total, 20 * 0.35 / 60)

    def test_invalid_parameters_are_rejected(self):
        cases = [
            {"dt_minutes": 0}, {"dt_minutes": -1}, {"dt_minutes": float("nan")},
            {"dt_minutes": float("inf")}, {"duration_hours": 0},
            {"walking_speed_kmh": 0}, {"taxi_speed_kmh": 0},
            {"road_distance_factor": 0}, {"rebalance_interval_min": 0},
            {"fleet_size": -1}, {"fleet_size": 1.5}, {"fleet_size": True},
            {"p_app": 1.1}, {"p_app": float("nan")},
            {"rebalance_fraction": -0.1}, {"rebalance_fraction": 1.1},
            {"demand_multiplier": -1}, {"event_multiplier": -1},
        ]
        for options in cases:
            with self.subTest(options=options), self.assertRaises(ValueError):
                make_sim(**options)

    def test_initialization_respects_all_stand_capacities(self):
        sim = make_sim(fleet_size=112, include_hubs=True)
        self.assertEqual(len(sim.taxis), 112)
        for sid, stand in sim.stands.items():
            self.assertEqual(sim.idle_taxis_at_stand(sid), stand.capacity)

    def test_fleet_larger_than_parking_capacity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "capacity"):
            make_sim(fleet_size=81)

    def test_zero_rebalance_fraction_never_relocates(self):
        sim = make_sim(fleet_size=8, rebalancing=True, rebalance_fraction=0, demand_multiplier=1)
        for taxi in sim.taxis.values():
            taxi.stand_id = 0
            taxi.pos = sim.stands[0].pos.copy()
        sim.current_time = 30
        sim.rebalance_fleet()
        self.assertTrue(all(t.state == "idle" for t in sim.taxis.values()))

    def test_small_positive_fraction_respects_transfer_limit(self):
        sim = make_sim(fleet_size=8, rebalancing=True, rebalance_fraction=0.25, demand_multiplier=1)
        for taxi in sim.taxis.values():
            taxi.stand_id = 0
            taxi.pos = sim.stands[0].pos.copy()
        sim.current_time = 30
        sim.rebalance_fleet()
        self.assertEqual(sum(t.state == "rebalancing" for t in sim.taxis.values()), 2)

    def test_fractional_event_forecast_has_correct_units(self):
        sim = make_sim(event_zone="NE")
        with patch.object(sim, "event_outbound_rate_per_minute", return_value=2):
            self.assertEqual(sim.expected_event_zone_rate(0, 0.25)["NE"], 120)


class ScenarioTests(unittest.TestCase):
    def test_replication_counts_and_summary_report_actual_sample_size(self):
        frame = run_replications("Test", n_rep=5, duration_hours=1 / 60, demand_multiplier=0)
        summary = summarize_experiments(frame)
        self.assertEqual(frame["replication"].tolist(), list(range(5)))
        self.assertEqual(summary.loc["Test", "replications"], 5)
        self.assertIn("avg_stand_walk_min", summary)
        self.assertIn("not_boarded_app", summary)
        self.assertIn("avg_app_wait_min_std", summary)

    def test_zero_replications_is_rejected(self):
        with self.assertRaises(ValueError):
            run_replications("Empty", n_rep=0)

    def test_real_demand_reconciles_states_times_and_capacities(self):
        sim = TaxiSimulation(
            duration_hours=8, seed=2026, event_zone="NE",
            event_start_hour=6, event_end_hour=7, event_attendance=50,
        )
        while sim.current_time < sim.duration_minutes:
            sim.step()
            for sid, stand in sim.stands.items():
                self.assertLessEqual(sim.idle_taxis_at_stand(sid), stand.capacity)
        metrics = sim.metrics()
        self.assertGreater(metrics["station_generated"], 0)
        self.assertGreater(metrics["airport_generated"], 0)
        self.assertGreater(metrics["event_generated"], 0)
        self.assertEqual(
            metrics["completed"] + metrics["onboard"] + metrics["not_boarded_app"]
            + metrics["not_boarded_stand"], metrics["generated"],
        )
        shares = sum(metrics[k] for k in (
            "availability_idle_share", "utilization_occupied_share", "empty_running_share"
        ))
        self.assertAlmostEqual(shares, 1)
        for p in sim.passengers.values():
            times = [p.request_time]
            if p.mode == "stand" and p.stand_arrival_time is not None:
                times.append(p.stand_arrival_time)
            if p.assignment_time is not None:
                times.append(p.assignment_time)
            if p.pickup_time is not None:
                times.append(p.pickup_time)
            if p.dropoff_time is not None:
                times.append(p.dropoff_time)
            self.assertEqual(times, sorted(times))
            self.assertLessEqual(times[-1], sim.current_time)


if __name__ == "__main__":
    unittest.main()
