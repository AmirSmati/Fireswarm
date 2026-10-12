
from models import (
    Incident,
    IncidentStatus,
    WorldEvent,
    WorldState,
)


def _record_event(
    world: WorldState,
    event_type: str,
    entity_id: str,
    message: str,
    severity: int = 1,
) -> WorldEvent:
    event = WorldEvent(
        event_type=event_type,
        tick=world.tick,
        entity_id=entity_id,
        message=message,
        severity=severity,
    )

    world.events.append(event)
    world.event_log.append(f"[tick {world.tick}] {message}")
    return event


def add_incident(
    world: WorldState,
    incident: Incident,
) -> WorldEvent:
    if incident.incident_id in world.incidents:
        raise ValueError(
            f"Incident already exists: {incident.incident_id}"
        )

    world.incidents[incident.incident_id] = incident

    return _record_event(
        world,
        "incident_detected",
        incident.incident_id,
        f"New incident detected: {incident.incident_id}",
        incident.severity,
    )


def escalate_incident(
    world: WorldState,
    incident_id: str,
    new_severity: int,
) -> WorldEvent:
    incident = world.incidents[incident_id]

    if incident.status != IncidentStatus.ACTIVE:
        raise ValueError("Cannot escalate an inactive incident")

    if not incident.severity < new_severity <= 5:
        raise ValueError("New severity must be higher, up to 5")

    incident.severity = new_severity

    return _record_event(
        world,
        "incident_escalated",
        incident_id,
        f"{incident_id} escalated to severity {new_severity}",
        new_severity,
    )


def extinguish_incident(
    world: WorldState,
    incident_id: str,
) -> WorldEvent:
    incident = world.incidents[incident_id]

    if incident.status != IncidentStatus.ACTIVE:
        raise ValueError("Incident is not active")

    incident.status = IncidentStatus.EXTINGUISHED

    return _record_event(
        world,
        "incident_extinguished",
        incident_id,
        f"{incident_id} has been extinguished",
        incident.severity,
    )
