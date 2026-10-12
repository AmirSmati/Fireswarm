
from simulation import create_initial_world


def test_initial_world():
    world = create_initial_world()

    assert len(world.drones) == 3
    assert len(world.incidents) == 2
    assert world.base_position == (10, 13)


def test_entities_are_inside_map():
    world = create_initial_world()

    for drone in world.drones.values():
        assert 0 <= drone.x < world.width
        assert 0 <= drone.y < world.height

    for incident in world.incidents.values():
        assert 0 <= incident.x < world.width
        assert 0 <= incident.y < world.height
