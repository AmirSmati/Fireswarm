
import pygame

from allocation import assign_available_drones
from events import add_incident,WorldEvent
from models import DroneStatus, Incident, IncidentStatus
from movement import advance_world
from renderer import Renderer
from simulation import create_initial_world

#2B Model
from decider_policy import choose_dispatch_policy, choose_reroute_decision

TICK_INTERVAL_MS = 1000


def reconsider_assignments(world, new_fire):
    if new_fire.status != IncidentStatus.ACTIVE:
        return

    # Do not send multiple drones to the same new fire.
    for drone in world.drones.values():
        if (
            drone.target_incident_id == new_fire.incident_id
            and drone.status in {
                DroneStatus.EN_ROUTE,
                DroneStatus.SUPPRESSING,
            }
        ):
            return

    for drone in world.drones.values():
        # First version: interrupt travelling drones only.
        if drone.status != DroneStatus.EN_ROUTE:
            continue

        current_fire = world.incidents.get(
            drone.target_incident_id
        )

        if current_fire is None:
            continue

        if current_fire.status != IncidentStatus.ACTIVE:
            continue

        # Only consider rerouting to a more severe fire.
        if new_fire.severity <= current_fire.severity:
            continue

        if drone.battery_pct < 15 or drone.water_pct < 20:
            continue

        state = (
            f"Drone: {drone.drone_id}\n"
            f"Drone position: ({drone.x}, {drone.y})\n"
            f"Battery: {drone.battery_pct:.1f}%\n"
            f"Water: {drone.water_pct:.1f}%\n"
            f"Current target: {current_fire.incident_id}\n"
            f"Current target severity: {current_fire.severity}\n"
            f"Current target position: "
            f"({current_fire.x}, {current_fire.y})\n"
            f"New fire: {new_fire.incident_id}\n"
            f"New fire severity: {new_fire.severity}\n"
            f"New fire position: ({new_fire.x}, {new_fire.y})\n"
            "Choose whether to keep the current target or "
            "reroute to the new fire."
        )

        try:
            decision, confidence = choose_reroute_decision(
                state,
                new_fire.incident_id,
            )
        except Exception as exc:
            print(
                f"[Decider] Rerouting request failed: {exc}. "
                "Keeping current assignment."
            )
            continue

        if decision == f"reroute_to_{new_fire.incident_id}":
            previous_target = drone.target_incident_id

            # Keep the drone en route, but change its destination.
            drone.target_incident_id = new_fire.incident_id

            message = (
                f"{drone.drone_id} rerouted from "
                f"{previous_target} to {new_fire.incident_id}"
            )

            world.events.append(
                WorldEvent(
                    event_type="drone_rerouted",
                    tick=world.tick,
                    entity_id=drone.drone_id,
                    message=message,
                    severity=new_fire.severity,
                )
            )
            world.event_log.append(
                f"[tick {world.tick}] {message}"
            )

            print(f"[Dispatcher] {message}")

            # One drone responds to this incident.
            break

def place_user_fire(world, x, y, severity=1):
    # Reject cells outside the world.
    if not (0 <= x < world.width and 0 <= y < world.height):
        return

    # The base cannot contain a fire.
    if (x, y) == world.base_position:
        print("Cannot place a fire on the base.")
        return

    # Do not place another incident on an occupied incident cell.
    occupied = any(
        incident.x == x and incident.y == y
        for incident in world.incidents.values()
    )

    if occupied:
        print("That cell already contains an incident.")
        return

    # Generate a unique incident ID.
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
    reconsider_assignments(world, incident)

    print(
        f"Created {incident.incident_id} "
        f"at ({x}, {y}), severity {severity}"
    )


def choose_policy_for_pending_fires(world):
    # Incidents already being handled are not candidates for a new assignment.
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
        and drone.battery_pct >= 15
        and drone.water_pct >= 20
    ]

    # No policy decision is needed when there's no competition.
    if len(pending) < 2 or not available:
        return "severity_first"

    fires_description = "\n".join(
        f"- {fire.incident_id}: severity={fire.severity}, "
        f"created_tick={fire.created_tick}, "
        f"position=({fire.x}, {fire.y})"
        for fire in pending
    )

    drones_description = "\n".join(
        f"- {drone.drone_id}: position=({drone.x}, {drone.y}), "
        f"battery={drone.battery_pct:.0f}%, "
        f"water={drone.water_pct:.0f}%"
        for drone in available
    )

    state = (
        f"Simulation tick: {world.tick}\n"
        f"Unassigned active fires:\n{fires_description}\n"
        f"Available drones:\n{drones_description}\n"
        f"There are {len(pending)} competing fires and "
        f"{len(available)} available drones. "
        "Choose the dispatch policy best suited to this situation."
    )

    try:
        policy, confidence = choose_dispatch_policy(state)
        return policy
    except Exception as exc:
        print(
            f"[Decider] Request failed: {exc}. "
            "Falling back to severity_first."
        )
        return "severity_first"

def main():
    world = create_initial_world()
    renderer = Renderer(world)

    running = True
    last_tick = pygame.time.get_ticks()

    def on_grid_click(x, y, severity):
        place_user_fire(world, x, y, severity)

    try:
        while running:
            running = renderer.draw(world, on_grid_click)

            if not running:
                break

            now = pygame.time.get_ticks()

            if now - last_tick >= TICK_INTERVAL_MS:
                policy = choose_policy_for_pending_fires(world)

                assignments = assign_available_drones(
                    world,
                    policy=policy,
                )

                if assignments:
                    print(
                        f"[Dispatcher] Policy={policy}; "
                        f"assignments={assignments}"
                    )

                advance_world(world)
                drone = next(iter(world.drones.values()))
                print(
                    f"[TEST] tick={world.tick} "
                    f"status={drone.status.value} "
                    f"target={drone.target_incident_id}"
                )
                last_tick = now

    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
