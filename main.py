import pygame

from allocation import assign_available_drones
from decider_policy import (
    choose_dispatch_policy,
    choose_reroute_decision,
    classify_response_policy,
)
from events import add_incident
from models import DroneStatus, Incident, IncidentStatus, WorldEvent, WorldState
from movement import advance_world
from renderer import Renderer
from simulation import create_initial_world


TICK_INTERVAL_MS = 1000
MIN_BATTERY_PCT = 15.0
MIN_WATER_PCT = 20.0
POLICY_MIN_CONFIDENCE = 0.50
CRITICAL_SEVERITY = 4


def record_world_event(
    world: WorldState,
    event_type: str,
    entity_id: str,
    message: str,
    severity: int = 1,
) -> None:
    """Add a structured event and a readable entry to the event log."""
    world.events.append(
        WorldEvent(
            event_type=event_type,
            tick=world.tick,
            entity_id=entity_id,
            message=message,
            severity=severity,
        )
    )
    world.event_log.append(f"[tick {world.tick}] {message}")


def record_assignment_events(world, assignments, source: str) -> None:
    """Record each assignment for the decision timeline and later evaluation."""
    for incident_id, drone_id in assignments.items():
        fire = world.incidents.get(incident_id)
        severity = fire.severity if fire is not None else 1
        message = f"{drone_id} assigned to {incident_id} via {source}"
        record_world_event(
            world,
            event_type="drone_assigned",
            entity_id=drone_id,
            message=message,
            severity=severity,
        )



def grid_distance(start, target):
    """Manhattan distance between two grid positions."""
    return abs(start[0] - target[0]) + abs(start[1] - target[1])


def reconsider_assignments(world, new_fire):
    """Evaluate en-route drones, prioritizing those closest to the new fire."""

    if not can_reroute_to(world, new_fire):
        return

    candidates = []

    # Gather ALL eligible drones before selecting one.
    for drone in world.drones.values():
        if drone.status != DroneStatus.EN_ROUTE:
            continue

        if (
            drone.battery_pct < MIN_BATTERY_PCT
            or drone.water_pct < MIN_WATER_PCT
        ):
            continue

        current_fire = world.incidents.get(drone.target_incident_id)

        if current_fire is None:
            continue

        if current_fire.status != IncidentStatus.ACTIVE:
            continue

        # Only interrupt a less-severe assignment.
        if new_fire.severity <= current_fire.severity:
            continue

        current_position = (drone.x, drone.y)

        distance_to_new = grid_distance(
            current_position,
            (new_fire.x, new_fire.y),
        )

        distance_to_current = grid_distance(
            current_position,
            (current_fire.x, current_fire.y),
        )

        candidates.append({
            "drone": drone,
            "current_fire": current_fire,
            "distance_to_new": distance_to_new,
            "distance_to_current": distance_to_current,
            "severity_gain": new_fire.severity - current_fire.severity,
        })

    if not candidates:
        print(
            f"[Dispatcher] No eligible drone to reroute to "
            f"{new_fire.incident_id}."
        )
        return

    # Location is the primary criterion: closest to the new fire first.
    # Use severity gain and drone ID only to break ties.
    candidates.sort(
        key=lambda candidate: (
            candidate["distance_to_new"],
            -candidate["severity_gain"],
            candidate["drone"].drone_id,
        )
    )

    print(
        f"[Dispatcher] Reroute candidates for {new_fire.incident_id}:"
    )

    for candidate in candidates:
        drone = candidate["drone"]
        current_fire = candidate["current_fire"]

        print(
            f"  {drone.drone_id}: current=({drone.x}, {drone.y}), "
            f"distance_to_new={candidate['distance_to_new']}, "
            f"distance_to_current={candidate['distance_to_current']}, "
            f"current_target={current_fire.incident_id}"
        )

    # Ask Decider in nearest-first order.
    for candidate in candidates:
        drone = candidate["drone"]
        current_fire = candidate["current_fire"]

        state = (
            f"New critical fire: {new_fire.incident_id}\n"
            f"New fire severity: {new_fire.severity}\n"
            f"New fire position: ({new_fire.x}, {new_fire.y})\n"
            f"Drone under consideration: {drone.drone_id}\n"
            f"Drone current position: ({drone.x}, {drone.y})\n"
            f"Manhattan distance from current position to new fire: "
            f"{candidate['distance_to_new']} grid steps\n"
            f"Current target: {current_fire.incident_id}\n"
            f"Current target severity: {current_fire.severity}\n"
            f"Current target position: "
            f"({current_fire.x}, {current_fire.y})\n"
            f"Distance from drone to current target: "
            f"{candidate['distance_to_current']} grid steps\n"
            f"Battery: {drone.battery_pct:.1f}%\n"
            f"Water: {drone.water_pct:.1f}%\n"
            "This candidate was selected based on its current position. "
            "Decide whether to reroute this drone or keep its assignment."
        )

        try:
            decision, confidence = choose_reroute_decision(
                state,
                new_fire.incident_id,
            )
        except Exception as exc:
            print(
                f"[Decider] Request failed for {drone.drone_id}: {exc}"
            )
            continue

        print(
            f"[Decider] Candidate={drone.drone_id}; "
            f"decision={decision}; confidence={confidence:.3f}"
        )

        record_world_event(
            world,
            event_type="reroute_decision",
            entity_id=drone.drone_id,
            message=(
                f"Decision={decision}; confidence={confidence:.3f}; "
                f"distance_to_new={candidate['distance_to_new']}; "
                f"target={new_fire.incident_id}"
            ),
            severity=new_fire.severity,
        )

        if decision != f"reroute_to_{new_fire.incident_id}":
            # This drone stays on its current assignment.
            continue

        previous_target = drone.target_incident_id

        # Keep EN_ROUTE status; movement uses the new target next tick.
        drone.target_incident_id = new_fire.incident_id

        message = (
            f"{drone.drone_id} rerouted from {previous_target} "
            f"to {new_fire.incident_id}; "
            f"distance_to_new={candidate['distance_to_new']}"
        )

        record_world_event(
            world,
            event_type="drone_rerouted",
            entity_id=drone.drone_id,
            message=message,
            severity=new_fire.severity,
        )

        print(f"[Dispatcher] {message}")
        break


def place_user_fire(world, x: int, y: int, severity: int = 1):
    """Create a fire from a grid click, validating the requested cell."""
    if not (0 <= x < world.width and 0 <= y < world.height):
        return None

    if not isinstance(severity, int) or not 1 <= severity <= 5:
        print("Fire severity must be an integer from 1 to 5.")
        return None

    if (x, y) == world.base_position:
        print("Cannot place a fire on the base.")
        return None

    occupied = any(
        incident.x == x and incident.y == y
        for incident in world.incidents.values()
    )
    if occupied:
        print("That cell already contains an incident.")
        return None

    number = 1
    while f"user_fire_{number:03d}" in world.incidents:
        number += 1

    incident = Incident(
        incident_id=f"user_fire_{number:03d}",
        x=x,
        y=y,
        severity=severity,
        spread_per_tick=0.1,
        created_tick=world.tick,
    )
    add_incident(world, incident)

    print(
        f"Created {incident.incident_id} at ({x}, {y}), "
        f"severity {severity}"
    )
    return incident


def choose_policy_for_pending_fires(world) -> str:
    """Select a dispatch ordering policy only when fires compete."""
    claimed_ids = {
        drone.target_incident_id
        for drone in world.drones.values()
        if drone.target_incident_id is not None
        and drone.status in {
            DroneStatus.EN_ROUTE,
            DroneStatus.SUPPRESSING,
        }
    }

    pending = [
        fire
        for fire in world.incidents.values()
        if fire.status == IncidentStatus.ACTIVE
        and fire.incident_id not in claimed_ids
    ]
    available = [
        drone
        for drone in world.drones.values()
        if drone.status == DroneStatus.IDLE
        and drone.battery_pct >= MIN_BATTERY_PCT
        and drone.water_pct >= MIN_WATER_PCT
    ]

    if len(pending) < 2 or not available:
        return "severity_first"

    fires_description = "\n".join(
        f"- {fire.incident_id}: severity={fire.severity}, "
        f"created_tick={fire.created_tick}, position=({fire.x}, {fire.y})"
        for fire in pending
    )
    drones_description = "\n".join(
        f"- {drone.drone_id}: position=({drone.x}, {drone.y}), "
        f"battery={drone.battery_pct:.0f}%, water={drone.water_pct:.0f}%"
        for drone in available
    )
    state = (
        f"Simulation tick: {world.tick}\n"
        f"Unassigned active fires:\n{fires_description}\n"
        f"Available drones:\n{drones_description}\n"
        f"There are {len(pending)} competing fires and {len(available)} "
        "available drones. Choose the dispatch policy best suited to this situation."
    )

    try:
        policy, confidence = choose_dispatch_policy(state)
        message = f"Dispatch policy selected: {policy}; confidence={confidence:.3f}"
        print(f"[Decider] {message}")
        record_world_event(
            world,
            event_type="dispatch_policy_selected",
            entity_id=pending[0].incident_id,
            message=message,
            severity=pending[0].severity,
        )
        return policy
    except Exception as exc:
        print(f"[Decider] Dispatch policy request failed: {exc}. Using severity_first.")
        record_world_event(
            world,
            event_type="dispatch_policy_fallback",
            entity_id=pending[0].incident_id,
            message=f"Dispatch policy fallback to severity_first: {exc}",
            severity=pending[0].severity,
        )
        return "severity_first"


def build_policy_context(world, event, incident) -> str:
    drone_lines = [
        f"- {drone.drone_id}: status={drone.status.value}, "
        f"position=({drone.x}, {drone.y}), target={drone.target_incident_id}, "
        f"battery={drone.battery_pct:.1f}%, water={drone.water_pct:.1f}%"
        for drone in world.drones.values()
    ]
    fire_lines = [
        f"- {fire.incident_id}: severity={fire.severity}, "
        f"status={fire.status.value}, position=({fire.x}, {fire.y}), "
        f"created_tick={fire.created_tick}"
        for fire in world.incidents.values()
        if fire.status == IncidentStatus.ACTIVE
    ]
    return (
        f"Incoming event: {event.event_type}\n"
        f"Incident: {incident.incident_id}\n"
        f"Severity: {incident.severity}\n"
        f"Position: ({incident.x}, {incident.y})\n"
        f"Simulation tick: {world.tick}\n"
        f"Active incidents:\n{chr(10).join(fire_lines)}\n"
        f"Drone state:\n{chr(10).join(drone_lines)}\n"
        "Classify the appropriate response category before action."
    )


def recover_low_resource_drones(world):
    """Return active drones with insufficient battery or water to base."""
    recovered = []
    for drone in world.drones.values():
        if drone.status not in {
            DroneStatus.EN_ROUTE,
            DroneStatus.SUPPRESSING,
        }:
            continue

        if (
            drone.battery_pct >= MIN_BATTERY_PCT
            and drone.water_pct >= MIN_WATER_PCT
        ):
            continue

        previous_target = drone.target_incident_id
        drone.status = DroneStatus.RETURNING
        drone.target_incident_id = None
        message = (
            f"{drone.drone_id} returning to base for resources; "
            f"previous target={previous_target}"
        )
        record_world_event(
            world,
            event_type="resource_recovery_started",
            entity_id=drone.drone_id,
            message=message,
        )
        print(f"[Dispatcher] {message}")
        recovered.append(drone.drone_id)

    if not recovered:
        print(
            "[Dispatcher] Resource recovery selected, but no en-route "
            "or suppressing drone met the resource thresholds."
        )
    return recovered


def has_available_drone(world) -> bool:
    return any(
        drone.status == DroneStatus.IDLE
        and drone.battery_pct >= MIN_BATTERY_PCT
        and drone.water_pct >= MIN_WATER_PCT
        for drone in world.drones.values()
    )


def has_low_resource_drone(world) -> bool:
    return any(
        drone.status in {
            DroneStatus.EN_ROUTE,
            DroneStatus.SUPPRESSING,
        }
        and (
            drone.battery_pct < MIN_BATTERY_PCT
            or drone.water_pct < MIN_WATER_PCT
        )
        for drone in world.drones.values()
    )


def can_reroute_to(world, incident) -> bool:
    """Return whether at least one eligible en-route drone can be redirected."""
    if incident.status != IncidentStatus.ACTIVE:
        return False

    if incident.severity < 4:
        return False

    # Prefer a ready idle drone over interrupting a mission.
    if has_available_drone(world):
        return False
    
    if incident.status != IncidentStatus.ACTIVE:
        return False
    if incident.severity < CRITICAL_SEVERITY:
        return False

    # Do not send another drone to an incident that already has an assigned drone.
    if any(
        drone.target_incident_id == incident.incident_id
        and drone.status in {
            DroneStatus.EN_ROUTE,
            DroneStatus.SUPPRESSING,
        }
        for drone in world.drones.values()
    ):
        return False

    for drone in world.drones.values():
        if drone.status != DroneStatus.EN_ROUTE:
            continue
        if (
            drone.battery_pct < MIN_BATTERY_PCT
            or drone.water_pct < MIN_WATER_PCT
        ):
            continue

        current_fire = world.incidents.get(drone.target_incident_id)
        if current_fire is None or current_fire.status != IncidentStatus.ACTIVE:
            continue
        if incident.severity > current_fire.severity:
            return True

    return False


def fallback_response_category(world, incident) -> str:
    """Choose a feasible fallback category without model inference."""
    if can_reroute_to(world, incident) and not has_available_drone(world):
        return "critical_reroute"
    if has_low_resource_drone(world):
        return "resource_recovery"
    if has_available_drone(world):
        return "routine_dispatch"
    return "maintain_assignments"


def handle_incident_policy_event(world, event) -> None:
    """Classify incident events, validate the category, and execute its handler."""
    if event.event_type not in {"incident_detected", "incident_escalated"}:
        return

    incident = world.incidents.get(event.entity_id)
    if incident is None or incident.status != IncidentStatus.ACTIVE:
        return

    state = build_policy_context(world, event, incident)
    try:
        category, confidence = classify_response_policy(state)
        if confidence < POLICY_MIN_CONFIDENCE:
            print(
                f"[Policy] Low confidence ({confidence:.3f}); "
                "using deterministic fallback."
            )
            category = fallback_response_category(world, incident)
            decision_source = "fallback_low_confidence"
        else:
            decision_source = "decider"
    except Exception as exc:
        print(f"[Policy] Classification failed: {exc}. Using deterministic fallback.")
        category = fallback_response_category(world, incident)
        confidence = 0.0
        decision_source = "fallback_error"

    # The coordinator applies hard feasibility checks before executing a category.
    if category == "critical_reroute":
        if has_available_drone(world):
            print(
                "[Guardrail] An eligible idle drone is available; "
                "using routine_dispatch instead of interrupting an assignment."
            )
            category = "routine_dispatch"
            decision_source = "fallback_guardrail"
        elif not can_reroute_to(world, incident):
            print(
                f"[Guardrail] Rejecting critical_reroute for {incident.incident_id}: "
                "no eligible rerouting action."
            )
            category = fallback_response_category(world, incident)
            decision_source = "fallback_guardrail"

    if category == "routine_dispatch" and not has_available_drone(world):
        category = fallback_response_category(world, incident)
        decision_source = "fallback_guardrail"

    if category == "resource_recovery" and not has_low_resource_drone(world):
        category = fallback_response_category(world, incident)
        decision_source = "fallback_guardrail"

    message = (
        f"Category={category}; confidence={confidence:.3f}; "
        f"event={event.event_type}; source={decision_source}"
    )
    print(
        f"[Policy] Event={event.event_type}; incident={incident.incident_id}; "
        f"severity={incident.severity}; {message}"
    )
    record_world_event(
        world,
        event_type="policy_classified",
        entity_id=incident.incident_id,
        message=message,
        severity=incident.severity,
    )

    if category == "critical_reroute":
        reconsider_assignments(world, incident)

    elif category == "routine_dispatch":
        dispatch_policy = choose_policy_for_pending_fires(world)
        assignments = assign_available_drones(world, policy=dispatch_policy)
        record_assignment_events(world, assignments, "routine_dispatch")
        if assignments:
            print(
                f"[Dispatcher] Policy={dispatch_policy}; assignments={assignments}"
            )

    elif category == "maintain_assignments":
        print("[Dispatcher] Existing assignments remain unchanged.")

    elif category == "resource_recovery":
        recover_low_resource_drones(world)


def process_new_world_events(world, last_processed_index: int) -> int:
    """Handle newly generated incident events once, without recursively handling logs."""
    new_events = world.events[last_processed_index:]
    for event in new_events:
        handle_incident_policy_event(world, event)
    # Actions may append timeline events; mark those as processed as well.
    return len(world.events)


def main() -> None:
    world = create_initial_world()
    renderer = Renderer(world)

    running = True
    last_tick = pygame.time.get_ticks()
    last_processed_event_index = len(world.events)

    def on_grid_click(x, y, severity):
        place_user_fire(world, x, y, severity)

    try:
        while running:
            running = renderer.draw(world, on_grid_click)
            if not running:
                break

            # Process incidents created through the interface.
            last_processed_event_index = process_new_world_events(
                world, last_processed_event_index
            )

            now = pygame.time.get_ticks()
            if now - last_tick >= TICK_INTERVAL_MS:
                # Deterministic tick allocation ensures idle drones can be
                # reassigned even if no new incident event occurs.
                assignments = assign_available_drones(
                    world,
                    policy="severity_first",
                )
                record_assignment_events(world, assignments, "fallback")
                if assignments:
                    print(f"[Dispatcher] Fallback assignments={assignments}")

                advance_world(world)

                # Process escalations and other events created by world progression.
                last_processed_event_index = process_new_world_events(
                    world, last_processed_event_index
                )
                last_tick = now

    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
