from allocation import assign_available_drones
from simulation import create_initial_world
from models import DroneStatus


def test_assignments_are_unique():
    world = create_initial_world()

    assignments = assign_available_drones(world)

    assert len(assignments) == 2
    assert len(set(assignments.values())) == 2


def test_more_severe_fire_gets_assigned_first():
    world = create_initial_world()

    assignments = assign_available_drones(world)

    assert "fire-2" in assignments
    assert "fire-1" in assignments


def test_assigned_drone_has_matching_target():
    world = create_initial_world()

    assignments = assign_available_drones(world)

    for fire_id, drone_id in assignments.items():
        drone = world.drones[drone_id]
        assert drone.target_incident_id == fire_id
        assert drone.status == DroneStatus.EN_ROUTE

def test_repeated_dispatch_does_not_duplicate_assignments():
    world = create_initial_world()

    first = assign_available_drones(world)
    second = assign_available_drones(world)

    assert len(first) == 2
    assert second == {}