
from models import Drone, Incident, WorldState
from mission_feasibility import (
    can_complete_mission,
    estimate_mission,
)


def make_world(
    *,
    severity=1,
    spread_per_tick=0.0,
    battery=100.0,
    water=100.0,
):
    drone = Drone(
        drone_id="drone-1",
        x=0,
        y=0,
        battery_pct=battery,
        water_pct=water,
    )

    incident = Incident(
        incident_id="fire-1",
        x=1,
        y=0,
        severity=severity,
        spread_per_tick=spread_per_tick,
        created_tick=0,
    )

    world = WorldState(
        width=10,
        height=10,
        base_position=(0, 0),
        drones={"drone-1": drone},
        incidents={"fire-1": incident},
    )

    return world, drone, incident


def test_severity_one_requires_20_water_without_spread():
    world, drone, fire = make_world(severity=1)

    estimate = estimate_mission(world, drone, fire)

    assert estimate.suppression_ticks == 4
    assert estimate.water_required == 20.0
    assert estimate.severity_at_arrival == 1
    assert can_complete_mission(world, drone, fire)


def test_severity_five_requires_100_water_without_spread():
    world, drone, fire = make_world(severity=5)

    estimate = estimate_mission(world, drone, fire)

    assert estimate.suppression_ticks == 20
    assert estimate.water_required == 100.0
    assert can_complete_mission(world, drone, fire)


def test_insufficient_water_rejects_severity_five():
    world, drone, fire = make_world(
        severity=5,
        water=80.0,
    )

    estimate = estimate_mission(world, drone, fire)

    assert estimate.water_required == 100.0
    assert not can_complete_mission(world, drone, fire)


def test_insufficient_battery_rejects_mission():
    world, drone, fire = make_world(
        severity=1,
        battery=2.0,
    )

    estimate = estimate_mission(world, drone, fire)

    assert estimate.battery_required > drone.battery_pct
    assert not can_complete_mission(world, drone, fire)


def test_spreading_fire_increases_required_water():
    world, drone, fire = make_world(
        severity=2,
        spread_per_tick=0.5,
    )

    estimate = estimate_mission(world, drone, fire)

    assert estimate.severity_at_arrival >= 2
    assert estimate.severity_at_extinguish > estimate.severity_at_arrival
    assert estimate.suppression_ticks > 4
    assert estimate.water_required > 20.0
