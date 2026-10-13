
import pygame

from allocation import assign_available_drones
from events import add_incident
from models import DroneStatus, Incident, IncidentStatus
from movement import advance_world
from renderer import Renderer
from simulation import create_initial_world

#2B Model
from decider_policy import choose_dispatch_policy

TICK_INTERVAL_MS = 1000


def place_user_fire(world, x, y):
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
        severity=1,
        spread_per_tick=0.1,
        created_tick=world.tick,
    )

    add_incident(world, incident)

    print(
        f"Created {incident.incident_id} "
        f"at ({x}, {y}), severity 1"
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

    def on_grid_click(x, y):
        place_user_fire(world, x, y)

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
                last_tick = now

    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
