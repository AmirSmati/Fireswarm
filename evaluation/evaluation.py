"""Compare the baseline dispatcher with the Decider-enabled dispatcher.

Run from the project root with the local Strands Decider server running:
    python evaluation.py

This is a controlled demonstration scenario, not a statistically robust benchmark.
"""

from __future__ import annotations

import csv
import time
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
RESULTS_PATH = Path("evaluation_results.csv")


def build_world() -> WorldState:
    """Create a deterministic world with three drones and no initial fires."""
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

    # Three remote, low-severity fires keep all drones busy during the warm-up.
    # Spread is disabled here to isolate dispatch/rerouting behavior.
    initial_fires = [
        Incident(
            incident_id="low_fire_a",
            x=1,
            y=1,
            severity=1,
            spread_per_tick=0.0,
            created_tick=0,
        ),
        Incident(
            incident_id="low_fire_b",
            x=3,
            y=5,
            severity=1,
            spread_per_tick=0.0,
            created_tick=0,
        ),
        Incident(
            incident_id="low_fire_c",
            x=18,
            y=2,
            severity=1,
            spread_per_tick=0.0,
            created_tick=0,
        ),
    ]

    for fire in initial_fires:
        add_incident(world, fire)

    assignments = assign_available_drones(world, policy="severity_first")
    record_assignment_events(world, assignments, "evaluation_setup")

    if len(assignments) != 3:
        raise RuntimeError(
            "Evaluation setup failed: expected all three drones to be assigned, "
            f"got {assignments!r}."
        )

    # Let the drones travel for the same number of ticks in both runs.
    for _ in range(WARMUP_TICKS):
        advance_world(world)

    return world


def observe_critical_fire(world: WorldState, metrics: dict) -> None:
    """Capture first dispatch, arrival, and extinguishing ticks for the critical fire."""
    fire = world.incidents[CRITICAL_FIRE_ID]

    if metrics["dispatch_tick"] is None:
        if any(
            drone.target_incident_id == CRITICAL_FIRE_ID
            and drone.status in {DroneStatus.EN_ROUTE, DroneStatus.SUPPRESSING}
            for drone in world.drones.values()
        ):
            metrics["dispatch_tick"] = world.tick

    if metrics["arrival_tick"] is None:
        if any(
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


def run_scenario(use_decider: bool) -> dict:
    label = "decider" if use_decider else "baseline"
    print(f"\n{'=' * 18} {label.upper()} RUN {'=' * 18}")

    world = build_world()
    critical_fire = Incident(
        incident_id=CRITICAL_FIRE_ID,
        x=10,
        y=4,
        severity=5,
        spread_per_tick=0.0,
        created_tick=world.tick,
    )
    critical_created_tick = world.tick

    # Start processing from this incident only, not the setup incidents.
    event_start_index = len(world.events)
    add_incident(world, critical_fire)

    metrics = {
        "mode": label,
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
        started = time.perf_counter()
        last_processed_event_index = process_new_world_events(
            world, last_processed_event_index
        )
        metrics["decision_wall_seconds"] += time.perf_counter() - started

    observe_critical_fire(world, metrics)
    event_index_for_reroute_count = event_start_index

    for _ in range(MAX_TICKS_AFTER_CRITICAL):
        # Both runs use the same deterministic baseline allocator whenever a
        # drone becomes available. Only the Decider run can preempt an assignment.
        assignments = assign_available_drones(world, policy="severity_first")
        if assignments:
            record_assignment_events(world, assignments, f"{label}_tick_allocation")

        observe_critical_fire(world, metrics)
        if metrics["extinguished_tick"] is not None:
            break

        previous_resources = {
            drone_id: (drone.battery_pct, drone.water_pct)
            for drone_id, drone in world.drones.items()
        }
        previous_event_count = len(world.events)
        advance_world(world)

        # Count resource consumption only when levels decrease, so refilling
        # does not cancel out earlier usage in this simple metric.
        for drone_id, drone in world.drones.items():
            previous_battery, previous_water = previous_resources[drone_id]
            metrics["battery_consumed_pct_points"] += max(
                0.0, previous_battery - drone.battery_pct
            )
            metrics["water_consumed_pct_points"] += max(
                0.0, previous_water - drone.water_pct
            )

        if use_decider:
            started = time.perf_counter()
            last_processed_event_index = process_new_world_events(
                world, previous_event_count
            )
            metrics["decision_wall_seconds"] += time.perf_counter() - started

        observe_critical_fire(world, metrics)
        if metrics["extinguished_tick"] is not None:
            break

    post_spawn_events = world.events[event_index_for_reroute_count:]
    reroutes = sum(
        event.event_type == "drone_rerouted" for event in post_spawn_events
    )

    metrics["dispatch_delay_ticks"] = elapsed_ticks(
        critical_created_tick, metrics["dispatch_tick"]
    )
    metrics["arrival_delay_ticks"] = elapsed_ticks(
        critical_created_tick, metrics["arrival_tick"]
    )
    metrics["extinguish_delay_ticks"] = elapsed_ticks(
        critical_created_tick, metrics["extinguished_tick"]
    )
    metrics["reroutes"] = reroutes
    metrics["finished"] = metrics["extinguished_tick"] is not None
    metrics["final_critical_severity"] = world.incidents[CRITICAL_FIRE_ID].severity
    metrics["decision_wall_seconds"] = round(
        metrics["decision_wall_seconds"], 3
    )
    metrics["battery_consumed_pct_points"] = round(
        metrics["battery_consumed_pct_points"], 1
    )
    metrics["water_consumed_pct_points"] = round(
        metrics["water_consumed_pct_points"], 1
    )

    print(
        f"{label}: dispatch={metrics['dispatch_delay_ticks']} ticks; "
        f"arrival={metrics['arrival_delay_ticks']} ticks; "
        f"extinguished={metrics['extinguish_delay_ticks']} ticks; "
        f"reroutes={metrics['reroutes']}; "
        f"decision time={metrics['decision_wall_seconds']} s; "
        f"finished={metrics['finished']}"
    )
    return metrics


def main() -> None:
    baseline = run_scenario(use_decider=False)
    decider = run_scenario(use_decider=True)
    rows = [baseline, decider]

    fieldnames = list(rows[0].keys())
    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\nCOMPARISON")
    print(f"{'Metric':<34} {'Baseline':>18} {'Decider 2B':>18}")
    print("-" * 72)
    columns = [
        ("Dispatch delay (ticks)", "dispatch_delay_ticks"),
        ("Arrival delay (ticks)", "arrival_delay_ticks"),
        ("Extinguish delay (ticks)", "extinguish_delay_ticks"),
        ("Reroutes", "reroutes"),
        ("Decision overhead (seconds)", "decision_wall_seconds"),
        ("Battery consumed (percentage points)", "battery_consumed_pct_points"),
        ("Water consumed (percentage points)", "water_consumed_pct_points"),
        ("Critical fire extinguished", "finished"),
    ]
    for label, key in columns:
        print(f"{label:<34} {str(baseline[key]):>18} {str(decider[key]):>18}")

    print(f"\nSaved raw results to: {RESULTS_PATH.resolve()}")
    print(
        "Note: this is one controlled scenario. Repeat with multiple layouts "
        "and runs before drawing general conclusions."
    )


if __name__ == "__main__":
    main()
