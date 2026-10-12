from models import (
    DroneStatus,
    IncidentStatus,
    WorldEvent,
    WorldState,
)

from events import extinguish_incident
from fire_dynamics import advance_fire_spread

def _record(world, event_type, drone_id, message):
    event = WorldEvent(
        event_type=event_type,
        tick=world.tick,
        entity_id=drone_id,
        message=message,
    )
    world.events.append(event)
    world.event_log.append(f"[tick {world.tick}] {message}")


def _move_one_cell(drone, destination):
    """Move horizontally first, then vertically."""
    target_x, target_y = destination

    if drone.x < target_x:
        drone.x += 1
    elif drone.x > target_x:
        drone.x -= 1
    elif drone.y < target_y:
        drone.y += 1
    elif drone.y > target_y:
        drone.y -= 1

    return (drone.x, drone.y) == destination


def request_return_to_base(world, drone_id):
    drone = world.drones[drone_id]

    if drone.status == DroneStatus.DISABLED:
        raise ValueError("Disabled drone cannot return autonomously")

    if drone.status in {DroneStatus.RETURNING, DroneStatus.REFILLING}:
        return

    drone.status = DroneStatus.RETURNING
    drone.target_incident_id = None
    _record(world, "return_requested", drone_id,
            f"{drone_id} returning to base")


def advance_world(world, battery_drain_per_move=0.5):
    """Advance the world by one simulation tick."""
    world.tick += 1
    
    advance_fire_spread(world)

    for drone in world.drones.values():

        # Release a task if its incident is no longer active.
        if drone.status in {
            DroneStatus.EN_ROUTE,
            DroneStatus.SUPPRESSING,
        }:
            incident = world.incidents.get(drone.target_incident_id)

            if incident is None or incident.status != IncidentStatus.ACTIVE:
                drone.target_incident_id = None
                drone.status = DroneStatus.IDLE
                _record(world, "task_released", drone.drone_id,
                        f"{drone.drone_id} released inactive target")
                continue

        
        if drone.status == DroneStatus.EN_ROUTE:
            incident = world.incidents[drone.target_incident_id]
            arrived = _move_one_cell(drone, (incident.x, incident.y))

            drone.battery_pct = max(
                0.0, drone.battery_pct - battery_drain_per_move
            )

            if drone.battery_pct <= 0:
                drone.status = DroneStatus.DISABLED
                drone.target_incident_id = None
                _record(world, "drone_disabled", drone.drone_id,
                        f"{drone.drone_id} battery depleted")
            elif arrived:
                drone.status = DroneStatus.SUPPRESSING
                _record(world, "drone_arrived", drone.drone_id,
                        f"{drone.drone_id} arrived at {incident.incident_id}")

        elif drone.status == DroneStatus.SUPPRESSING:
            incident = world.incidents[drone.target_incident_id]

            if drone.water_pct <= 0:
                request_return_to_base(world, drone.drone_id)
                continue

            incident.suppression_progress = min(
                100.0,
                incident.suppression_progress + 25.0 / incident.severity,
            )
            drone.water_pct = max(0.0, drone.water_pct - 5.0)
            drone.battery_pct = max(0.0, drone.battery_pct - 0.25)

            if incident.suppression_progress >= 100.0:
                extinguish_incident(world, incident.incident_id)
                drone.status = DroneStatus.IDLE
                drone.target_incident_id = None
                _record(
                    world, "suppression_complete", drone.drone_id,
                    f"{drone.drone_id} extinguished {incident.incident_id}",
                )
            elif drone.battery_pct <= 0:
                drone.status = DroneStatus.DISABLED
                drone.target_incident_id = None
                _record(
                    world, "drone_disabled", drone.drone_id,
                    f"{drone.drone_id} battery depleted while suppressing",
                )
            elif drone.water_pct <= 0:
                request_return_to_base(world, drone.drone_id)
    
        elif drone.status == DroneStatus.RETURNING:
            arrived = _move_one_cell(drone, world.base_position)

            drone.battery_pct = max(
                0.0, drone.battery_pct - battery_drain_per_move
            )

            if drone.battery_pct == 0:
                drone.status = DroneStatus.DISABLED
                _record(world, "drone_disabled", drone.drone_id,
                        f"{drone.drone_id} battery depleted while returning")
            elif arrived:
                drone.status = DroneStatus.REFILLING
                _record(world, "drone_arrived_base", drone.drone_id,
                        f"{drone.drone_id} arrived at base")

        elif drone.status == DroneStatus.REFILLING:
            drone.battery_pct = min(100.0, drone.battery_pct + 20.0)
            drone.water_pct = min(100.0, drone.water_pct + 25.0)

            if drone.battery_pct == 100.0 and drone.water_pct == 100.0:
                drone.status = DroneStatus.IDLE
                _record(world, "drone_ready", drone.drone_id,
                        f"{drone.drone_id} refilled and ready")