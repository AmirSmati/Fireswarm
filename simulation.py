
from models import (
    Drone,
    Incident,
    WorldState,
)


def create_initial_world() -> WorldState:
    """Create a reproducible world for the first simulation."""

    world = WorldState()

    # Three drones staged at the base.
    bx, by = world.base_position

    for i, x_offset in enumerate([-1, 0, 1], start=1):
        drone_id = f"drone-{i}"

        world.drones[drone_id] = Drone(
            drone_id=drone_id,
            x=bx + x_offset,
            y=by,
        )

    # Two initial fires.
    world.incidents["fire-1"] = Incident(
        incident_id="fire-1",
        x=3,
        y=3,
        severity=2,
        spread_per_tick=0.15,
        created_tick=0,
    )

    world.incidents["fire-2"] = Incident(
        incident_id="fire-2",
        x=16,
        y=4,
        severity=4,
        spread_per_tick=0.35,
        created_tick=0,
    )

    world.event_log.extend([
        "World initialized.",
        "Three drones deployed at base.",
        "Fire-1 detected: severity 2.",
        "Fire-2 detected: severity 4.",
    ])

    return world


if __name__ == "__main__":
    world = create_initial_world()

    print(f"Map: {world.width} x {world.height}")
    print(f"Base: {world.base_position}")
    print(f"Drones: {len(world.drones)}")
    print(f"Incidents: {len(world.incidents)}")

    for drone in world.drones.values():
        print(
            f"{drone.drone_id}: "
            f"position=({drone.x}, {drone.y}), "
            f"battery={drone.battery_pct}%, "
            f"water={drone.water_pct}%"
        )

    for event in world.event_log:
        print(f"[EVENT] {event}")
