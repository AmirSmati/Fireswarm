from models import (
    DroneStatus,
    IncidentStatus,
    WorldState,
)


def distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Manhattan distance on our grid."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def assign_available_drones(
    world: WorldState,
    min_battery: float = 15.0,
    min_water: float = 20.0,
    policy: str = "severity_first",
) -> dict[str, str]:
    """
    Baseline dispatcher:
    - Prioritize more severe fires.
    - Assign the nearest available drone.
    - Avoid assigning one drone to multiple fires.
    - Exclude drones with insufficient resources.

    Returns {incident_id: drone_id}.
    """
    claimed_incident_ids = {
        drone.target_incident_id
        for drone in world.drones.values()
        if drone.target_incident_id is not None
        and drone.status in {
            DroneStatus.EN_ROUTE,
            DroneStatus.SUPPRESSING,
        }
    }

    
    if policy not in {"severity_first", "oldest_first"}:
        raise ValueError(f"Unknown dispatch policy: {policy}")

    incidents = [
        incident
        for incident in world.incidents.values()
        if incident.status == IncidentStatus.ACTIVE
        and incident.incident_id not in claimed_incident_ids
    ]

    if policy == "severity_first":
        incidents.sort(
            key=lambda incident: (
                -incident.severity,
                incident.created_tick,
                incident.incident_id,
            )
        )
    else:  # oldest_first
        incidents.sort(
            key=lambda incident: (
                incident.created_tick,
                -incident.severity,
                incident.incident_id,
            )
        )


    available = [
        drone
        for drone in world.drones.values()
        if drone.status == DroneStatus.IDLE
        and drone.battery_pct >= min_battery
        and drone.water_pct >= min_water
    ]

    assignments: dict[str, str] = {}

    for incident in incidents:
        if not available:
            break

        target = (incident.x, incident.y)

        drone = min(
            available,
            key=lambda d: (
                distance((d.x, d.y), target),
                d.drone_id,
            ),
        )

        drone.status = DroneStatus.EN_ROUTE
        drone.target_incident_id = incident.incident_id

        assignments[incident.incident_id] = drone.drone_id
        available.remove(drone)

    return assignments

