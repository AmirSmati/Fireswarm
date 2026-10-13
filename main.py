
import pygame

from allocation import assign_available_drones
from events import add_incident
from models import Incident
from movement import advance_world
from renderer import Renderer
from simulation import create_initial_world


TICK_INTERVAL_MS = 350


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
                assign_available_drones(world)
                advance_world(world)
                last_tick = now

    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
