from allocation import assign_available_drones
from events import extinguish_incident
from models import DroneStatus, IncidentStatus
from movement import (
    advance_world,
    request_return_to_base,
)
from simulation import create_initial_world


def test_drone_moves_toward_assigned_incident():
    world = create_initial_world()
    assignments = assign_available_drones(world)

    fire_id, drone_id = next(iter(assignments.items()))
    drone = world.drones[drone_id]
    fire = world.incidents[fire_id]

    before = abs(drone.x - fire.x) + abs(drone.y - fire.y)
    advance_world(world)
    after = abs(drone.x - fire.x) + abs(drone.y - fire.y)

    assert after == before - 1


def test_drone_enters_suppression_state_on_arrival():
    world = create_initial_world()
    assignments = assign_available_drones(world)

    fire_id, drone_id = next(iter(assignments.items()))
    drone = world.drones[drone_id]
    fire = world.incidents[fire_id]

    drone.x = fire.x - 1
    drone.y = fire.y

    advance_world(world)

    assert (drone.x, drone.y) == (fire.x, fire.y)
    assert drone.status == DroneStatus.SUPPRESSING


def test_extinguished_target_releases_drone():
    world = create_initial_world()
    assignments = assign_available_drones(world)

    fire_id, drone_id = next(iter(assignments.items()))
    extinguish_incident(world, fire_id)

    advance_world(world)

    drone = world.drones[drone_id]
    assert drone.status == DroneStatus.IDLE
    assert drone.target_incident_id is None


def test_drone_returns_and_refills():
    world = create_initial_world()
    drone = world.drones["drone-1"]

    drone.x, drone.y = 8, 13
    drone.battery_pct = 80
    drone.water_pct = 50

    request_return_to_base(world, drone.drone_id)

    for _ in range(10):
        advance_world(world)
        if drone.status == DroneStatus.REFILLING:
            break

    assert (drone.x, drone.y) == world.base_position
    assert drone.status == DroneStatus.REFILLING

    for _ in range(10):
        advance_world(world)
        if drone.status == DroneStatus.IDLE:
            break

    assert drone.status == DroneStatus.IDLE
    assert drone.battery_pct == 100
    assert drone.water_pct == 100
def test_drone_can_extinguish_fire():
    world = create_initial_world()
    assignments = assign_available_drones(world)

    fire_id, drone_id = next(iter(assignments.items()))
    fire = world.incidents[fire_id]
    drone = world.drones[drone_id]

    fire.severity = 1
    fire.spread_per_tick = 0
    drone.status = DroneStatus.SUPPRESSING
    drone.x, drone.y = fire.x, fire.y

    for _ in range(4):
        advance_world(world)

    assert fire.status == IncidentStatus.EXTINGUISHED
    assert drone.status == DroneStatus.RETURNING
    assert drone.target_incident_id is None