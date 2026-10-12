from events import escalate_incident
from models import IncidentStatus, WorldState


def advance_fire_spread(world: WorldState) -> None:
    for fire in world.incidents.values():
        if fire.status != IncidentStatus.ACTIVE or fire.severity >= 5:
            continue

        fire.spread_progress += fire.spread_per_tick

        while fire.spread_progress >= 1 and fire.severity < 5:
            fire.spread_progress -= 1
            escalate_incident(
                world, fire.incident_id, fire.severity + 1
            )