import pytest

from events import (
    add_incident,
    escalate_incident,
    extinguish_incident,
)
from models import Incident, IncidentStatus, WorldState, WorldEvent


def test_new_incident_emits_event():
    world = WorldState()
    fire = Incident("fire-3", 5, 5, severity=2)

    event = add_incident(world, fire)

    assert event.event_type == "incident_detected"
    assert world.incidents["fire-3"] is fire
    assert world.events[-1] is event


def test_escalation_updates_state_and_emits_event():
    world = WorldState()
    add_incident(world, Incident("fire-1", 2, 3, severity=2))

    event = escalate_incident(world, "fire-1", 5)

    assert world.incidents["fire-1"].severity == 5
    assert event.event_type == "incident_escalated"
    assert event.severity == 5


def test_extinguishing_fire_updates_state():
    world = WorldState()
    add_incident(world, Incident("fire-1", 2, 3))

    event = extinguish_incident(world, "fire-1")

    assert world.incidents["fire-1"].status == IncidentStatus.EXTINGUISHED
    assert event.event_type == "incident_extinguished"


def test_duplicate_incident_is_rejected():
    world = WorldState()
    fire = Incident("fire-1", 2, 3)
    add_incident(world, fire)

    with pytest.raises(ValueError):
        add_incident(world, fire)