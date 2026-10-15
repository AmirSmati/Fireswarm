"""Run paired baseline-vs-Decider evaluation across multiple layouts.

Run from the Firewatch Swarm project root with the local Decider server active:
    python evaluation_suite.py

Optional: set REPEATS below to change repeated trials per layout.
This is an engineering evaluation harness, not a statistically conclusive study.
"""

from __future__ import annotations

import csv
import io
import statistics
import time
from contextlib import redirect_stdout
from pathlib import Path

from allocation import assign_available_drones
from events import add_incident
from main import process_new_world_events, record_assignment_events
from models import Drone, DroneStatus, Incident, IncidentStatus, WorldState
from movement import advance_world


BASE_POSITION = (10, 13)
GRID_WIDTH = 20
GRID_HEIGHT = 14
WARMUP_TICKS = 3
MAX_TICKS_AFTER_CRITICAL = 180
CRITICAL_FIRE_ID = "critical_fire"
REPEATS = 3
RESULTS_PATH = Path("evaluation_suite_results.csv")

# Each layout uses the same three initial low/medium-severity fires in different
# locations. Spread is disabled to isolate dispatch and rerouting behavior.
SCENARIOS = [
    {
        "name": "center_north",
        "low_fires": [
            ("low_fire_a", 1, 1, 1),
            ("low_fire_b", 3, 5, 2),
            ("low_fire_c", 18, 2, 3),
        ],
        "critical_position": (10, 4),
        "critical_severity": 5,
    },
    {
        "name": "west",
        "low_fires": [
            ("low_fire_a", 12, 1, 1),
            ("low_fire_b", 16, 5, 2),
            ("low_fire_c", 18, 9, 3),
        ],
        "critical_position": (2, 2),
        "critical_severity": 5,
    },
    {
        "name": "east",
        "low_fires": [
            ("low_fire_a", 1, 2, 1),
            ("low_fire_b", 2, 7, 2),
            ("low_fire_c", 3, 10, 3),
        ],
        "critical_position": (18, 4),
        "critical_severity": 5,
    },
    {
        "name": "south_center",
        "low_fires": [
            ("low_fire_a", 1, 1, 1),
            ("low_fire_b", 18, 1, 2),
            ("low_fire_c", 2, 6, 3),
        ],
        "critical_position": (10, 10),
        "critical_severity": 4,
    },
    {
        "name": "cross_map",
        "low_fires": [
            ("low_fire_a", 1, 12, 1),
            ("low_fire_b", 18, 12, 2),
            ("low_fire_c", 4, 2, 3),
        ],
        "critical_position": (15, 6),
        "critical_severity": 5,
    },
]


def build_world(scenario: dict) -> WorldState:
    drones = {
        f"drone-{index}": Drone(
            drone_id=f"drone-{index}",
            x=BASE_POSITION[0],
            y=BASE_POSITION[1],
        )
        for index in range(1, 4)
    }
    world = WorldState(
        width=GRID_WIDTH,
        height=GRID_HEIGHT,
        base_position=BASE_POSITION,
        drones=drones,
    )

    for incident_id, x, y, severity in scenario["low_fires"]:
        add_incident(
            world,
            Incident(
                incident_id=incident_id,
                x=x,
                y=y,
                severity=severity,
                spread_per_tick=0.0,
                created_tick=0,
            ),
        )

    assignments = assign_available_drones(world, policy="severity_first")
    record_assignment_events(world, assignments, "evaluation_setup")
    if len(assignments) != len(drones):
        raise RuntimeError(
            f"Scenario {scenario['name']}: expected to assign all drones; "
            f"received {assignments!r}"
        )

    for _ in range(WARMUP_TICKS):
        advance_world(world)

    return world


def observe_critical_fire(world: WorldState, metrics: dict) -> None:
    fire = world.incidents[CRITICAL_FIRE_ID]

    if metrics["dispatch_tick"] is None and any(
        drone.target_incident_id == CRITICAL_FIRE_ID
        and drone.status in {DroneStatus.EN_ROUTE, DroneStatus.SUPPRESSING}
        for drone in world.drones.values()
    ):
        metrics["dispatch_tick"] = world.tick

    if metrics["arrival_tick"] is None and any(
        drone.target_incident_id == CRITICAL_FIRE_ID
        and drone.status == DroneStatus.SUPPRESSING
        for drone in world.drones.values()
    ):
        metrics["arrival_tick"] = world.tick

    if (
        metrics["extinguished_tick"] is None
        and fire.status == IncidentStatus.EXTINGUISHED
    ):
        metrics["extinguished_tick"] = world.tick


def elapsed_ticks(event_tick: int, observed_tick: int | None) -> int | str:
    if observed_tick is None:
        return "not reached"
    return max(0, observed_tick - event_tick)


def run_trial(scenario: dict, repeat: int, use_decider: bool) -> tuple[dict, str]:
    mode = "decider" if use_decider else "baseline"
    captured = io.StringIO()
    started_all = time.perf_counter()

    # Capture the per-event logs so a multi-run evaluation stays readable.
    with redirect_stdout(captured):
        world = build_world(scenario)
        critical_x, critical_y = scenario["critical_position"]
        critical_fire = Incident(
            incident_id=CRITICAL_FIRE_ID,
            x=critical_x,
            y=critical_y,
            severity=scenario["critical_severity"],
            spread_per_tick=0.0,
            created_tick=world.tick,
        )
        critical_created_tick = world.tick
        event_start_index = len(world.events)
        add_incident(world, critical_fire)

        metrics = {
            "scenario": scenario["name"],
            "repeat": repeat,
            "mode": mode,
            "critical_severity": scenario["critical_severity"],
            "critical_created_tick": critical_created_tick,
            "dispatch_tick": None,
            "arrival_tick": None,
            "extinguished_tick": None,
            "decision_wall_seconds": 0.0,
            "battery_consumed_pct_points": 0.0,
            "water_consumed_pct_points": 0.0,
        }

        last_processed_event_index = event_start_index
        if use_decider:
            decision_start = time.perf_counter()
            last_processed_event_index = process_new_world_events(
                world, last_processed_event_index
            )
            metrics["decision_wall_seconds"] += (
                time.perf_counter() - decision_start
            )

        observe_critical_fire(world, metrics)

        for _ in range(MAX_TICKS_AFTER_CRITICAL):
            # Both modes use identical baseline allocation for idle drones.
            # Only the Decider mode can preempt an en-route assignment.
            assignments = assign_available_drones(
                world, policy="severity_first"
            )
            if assignments:
                record_assignment_events(world, assignments, f"{mode}_tick_allocation")

            observe_critical_fire(world, metrics)
            if metrics["extinguished_tick"] is not None:
                break

            previous_resources = {
                drone_id: (drone.battery_pct, drone.water_pct)
                for drone_id, drone in world.drones.items()
            }
            previous_event_count = len(world.events)
            advance_world(world)

            # Sum decreases, including repeated deployments after refills.
            for drone_id, drone in world.drones.items():
                previous_battery, previous_water = previous_resources[drone_id]
                metrics["battery_consumed_pct_points"] += max(
                    0.0, previous_battery - drone.battery_pct
                )
                metrics["water_consumed_pct_points"] += max(
                    0.0, previous_water - drone.water_pct
                )

            if use_decider:
                decision_start = time.perf_counter()
                last_processed_event_index = process_new_world_events(
                    world, previous_event_count
                )
                metrics["decision_wall_seconds"] += (
                    time.perf_counter() - decision_start
                )

            observe_critical_fire(world, metrics)
            if metrics["extinguished_tick"] is not None:
                break

        post_spawn_events = world.events[event_start_index:]
        metrics["dispatch_delay_ticks"] = elapsed_ticks(
            critical_created_tick, metrics["dispatch_tick"]
        )
        metrics["arrival_delay_ticks"] = elapsed_ticks(
            critical_created_tick, metrics["arrival_tick"]
        )
        metrics["extinguish_delay_ticks"] = elapsed_ticks(
            critical_created_tick, metrics["extinguished_tick"]
        )
        metrics["reroutes"] = sum(
            event.event_type == "drone_rerouted"
            for event in post_spawn_events
        )
        metrics["policy_classifications"] = sum(
            event.event_type == "policy_classified"
            for event in post_spawn_events
        )
        metrics["reroute_decisions"] = sum(
            event.event_type == "reroute_decision"
            for event in post_spawn_events
        )
        metrics["finished"] = metrics["extinguished_tick"] is not None
        metrics["elapsed_wall_seconds"] = round(
            time.perf_counter() - started_all, 3
        )
        metrics["decision_wall_seconds"] = round(
            metrics["decision_wall_seconds"], 3
        )
        metrics["battery_consumed_pct_points"] = round(
            metrics["battery_consumed_pct_points"], 1
        )
        metrics["water_consumed_pct_points"] = round(
            metrics["water_consumed_pct_points"], 1
        )

    return metrics, captured.getvalue()


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def median_metric(rows: list[dict], key: str) -> float | None:
    values = [row[key] for row in rows if is_number(row.get(key))]
    return statistics.median(values) if values else None


def fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def main() -> None:
    all_rows: list[dict] = []
    paired: dict[tuple[str, int], dict[str, dict]] = {}

    total_runs = len(SCENARIOS) * REPEATS * 2
    print(
        f"Evaluating {len(SCENARIOS)} layouts x {REPEATS} repeats x 2 modes "
        f"= {total_runs} runs."
    )
    print("The local Decider server must be running for Decider trials.\n")

    for scenario in SCENARIOS:
        for repeat in range(1, REPEATS + 1):
            for use_decider in (False, True):
                mode = "decider" if use_decider else "baseline"
                metrics, captured_logs = run_trial(
                    scenario, repeat, use_decider
                )
                all_rows.append(metrics)
                paired.setdefault((scenario["name"], repeat), {})[mode] = metrics

                print(
                    f"{scenario['name']:<14} run={repeat} {mode:<8} "
                    f"dispatch={metrics['dispatch_delay_ticks']} "
                    f"arrival={metrics['arrival_delay_ticks']} "
                    f"extinguished={metrics['extinguish_delay_ticks']} "
                    f"reroutes={metrics['reroutes']} "
                    f"decision_s={metrics['decision_wall_seconds']} "
                    f"finished={metrics['finished']}"
                )

                if not metrics["finished"]:
                    print("  WARNING: critical fire was not extinguished in time.")
                # Keep logs hidden for concise output, but surface them if the
                # simulation failed to complete so issues can be diagnosed.
                if not metrics["finished"] and captured_logs.strip():
                    print(captured_logs[-5000:])

    fieldnames = list(all_rows[0].keys())
    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print("\nMEDIAN RESULTS ACROSS ALL TRIALS")
    print(f"{'Metric':<34}{'Baseline':>15}{'Decider 2B':>15}")
    print("-" * 64)
    for label, key in [
        ("Dispatch delay (ticks)", "dispatch_delay_ticks"),
        ("Arrival delay (ticks)", "arrival_delay_ticks"),
        ("Extinguish delay (ticks)", "extinguish_delay_ticks"),
        ("Reroutes", "reroutes"),
        ("Decision processing (seconds)", "decision_wall_seconds"),
        ("Total wall time (seconds)", "elapsed_wall_seconds"),
        ("Battery consumed (points)", "battery_consumed_pct_points"),
        ("Water consumed (points)", "water_consumed_pct_points"),
    ]:
        baseline_rows = [row for row in all_rows if row["mode"] == "baseline"]
        decider_rows = [row for row in all_rows if row["mode"] == "decider"]
        print(
            f"{label:<34}{fmt(median_metric(baseline_rows, key)):>15}"
            f"{fmt(median_metric(decider_rows, key)):>15}"
        )

    print("\nPAIRED OUTCOMES (positive means Decider used fewer ticks)")
    for label, key in [
        ("Arrival delay", "arrival_delay_ticks"),
        ("Extinguish delay", "extinguish_delay_ticks"),
    ]:
        deltas = []
        wins = ties = losses = 0
        for modes in paired.values():
            baseline = modes.get("baseline", {}).get(key)
            decider = modes.get("decider", {}).get(key)
            if not (is_number(baseline) and is_number(decider)):
                continue
            delta = baseline - decider
            deltas.append(delta)
            if delta > 0:
                wins += 1
            elif delta == 0:
                ties += 1
            else:
                losses += 1
        print(
            f"{label}: median improvement={fmt(statistics.median(deltas) if deltas else None)} ticks; "
            f"Decider faster={wins}, tied={ties}, slower={losses}"
        )

    baseline_finished = sum(
        row["finished"] for row in all_rows if row["mode"] == "baseline"
    )
    decider_finished = sum(
        row["finished"] for row in all_rows if row["mode"] == "decider"
    )
    baseline_n = sum(row["mode"] == "baseline" for row in all_rows)
    decider_n = sum(row["mode"] == "decider" for row in all_rows)
    print(
        f"\nCritical fire extinguished: baseline {baseline_finished}/{baseline_n}; "
        f"Decider {decider_finished}/{decider_n}"
    )
    print(f"Raw data saved to: {RESULTS_PATH.resolve()}")
    print(
        "Caution: repeated model calls are not guaranteed to be identical. "
        "Use this as exploratory evidence, not a statistically conclusive benchmark."
    )


if __name__ == "__main__":
    main()
