
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

def test_idle_drone_is_preferred_over_rerouting(monkeypatch):
    from models import Drone, DroneStatus, WorldEvent

    world, travelling_drone, new_fire = make_test_world()

    idle_drone = Drone(
        drone_id="drone-2",
        x=0,
        y=0,
        battery_pct=100.0,
        water_pct=100.0,
        status=DroneStatus.IDLE,
    )
    world.drones[idle_drone.drone_id] = idle_drone

    # The coordinator should recognize that rerouting isn't needed.
    assert not main.can_reroute_to(world, new_fire)

    # Simulate Decider recommending a reroute anyway.
    monkeypatch.setattr(
        main,
        "classify_response_policy",
        lambda state: ("critical_reroute", 0.95),
    )

    event = WorldEvent(
        event_type="incident_detected",
        tick=world.tick,
        entity_id=new_fire.incident_id,
        message="Critical fire detected",
        severity=new_fire.severity,
    )

    main.handle_incident_policy_event(world, event)

    # Keep the existing mission and use the idle drone instead.
    assert travelling_drone.target_incident_id == "old_fire"
    assert idle_drone.target_incident_id == new_fire.incident_id
    assert idle_drone.status == DroneStatus.EN_ROUTE


def test_returning_drone_can_be_redirected(monkeypatch):
    world, drone, new_fire = make_test_world()

    drone.status = DroneStatus.RETURNING
    drone.target_incident_id = None
    drone.battery_pct = 80.0
    drone.water_pct = 80.0

    monkeypatch.setattr(
        main,
        "choose_reroute_decision",
        lambda state, incident_id: (
            f"reroute_to_{incident_id}", 0.95
        ),
    )

    main.reconsider_assignments(world, new_fire)

    assert drone.status == DroneStatus.EN_ROUTE
    assert drone.target_incident_id == new_fire.incident_id


def test_returning_drone_with_low_resources_is_not_redirected(
    monkeypatch,
):
    world, drone, new_fire = make_test_world()

    drone.status = DroneStatus.RETURNING
    drone.target_incident_id = None
    drone.battery_pct = 10.0
    drone.water_pct = 80.0

    monkeypatch.setattr(
        main,
        "choose_reroute_decision",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("Decider should not be called")
        ),
    )

    main.reconsider_assignments(world, new_fire)

    assert drone.status == DroneStatus.RETURNING
    assert drone.target_incident_id is None
