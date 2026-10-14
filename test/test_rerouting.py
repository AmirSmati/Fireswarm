
import main
from models import (
    Drone,
    DroneStatus,
    Incident,
    WorldState,
)


def make_test_world(
    current_severity=1,
    new_severity=5,
    battery=100.0,
    water=100.0,
):
    drone = Drone(
        drone_id="drone-1",
        x=2,
        y=2,
        battery_pct=battery,
        water_pct=water,
        status=DroneStatus.EN_ROUTE,
        target_incident_id="old_fire",
    )

    old_fire = Incident(
        incident_id="old_fire",
        x=5,
        y=5,
        severity=current_severity,
    )

    new_fire = Incident(
        incident_id="new_fire",
        x=9,
        y=9,
        severity=new_severity,
    )

    world = WorldState(
        drones={"drone-1": drone},
        incidents={
            "old_fire": old_fire,
            "new_fire": new_fire,
        },
    )

    return world, drone, new_fire


def test_decider_can_reroute_drone(monkeypatch):
    world, drone, new_fire = make_test_world()

    monkeypatch.setattr(
        main,
        "choose_reroute_decision",
        lambda state, incident_id: (
            f"reroute_to_{incident_id}", 0.95
        ),
    )

    main.reconsider_assignments(world, new_fire)

    assert drone.target_incident_id == "new_fire"
    assert drone.status == DroneStatus.EN_ROUTE
    assert any(
        event.event_type == "drone_rerouted"
        for event in world.events
    )


def test_decider_can_keep_current_target(monkeypatch):
    world, drone, new_fire = make_test_world()

    monkeypatch.setattr(
        main,
        "choose_reroute_decision",
        lambda state, incident_id: ("keep_current", 0.95),
    )

    main.reconsider_assignments(world, new_fire)

    assert drone.target_incident_id == "old_fire"


def test_equal_severity_does_not_trigger_rerouting(monkeypatch):
    world, drone, new_fire = make_test_world(
        current_severity=3,
        new_severity=3,
    )

    def unexpected_decision(*args):
        raise AssertionError("Decider should not be called")

    monkeypatch.setattr(
        main, "choose_reroute_decision", unexpected_decision
    )

    main.reconsider_assignments(world, new_fire)

    assert drone.target_incident_id == "old_fire"


def test_insufficient_resources_prevent_rerouting(monkeypatch):
    world, drone, new_fire = make_test_world(battery=10.0)

    def unexpected_decision(*args):
        raise AssertionError("Decider should not be called")

    monkeypatch.setattr(
        main, "choose_reroute_decision", unexpected_decision
    )

    main.reconsider_assignments(world, new_fire)

    assert drone.target_incident_id == "old_fire"
