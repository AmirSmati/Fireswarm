
from dataclasses import dataclass
from math import ceil

from models import Drone, Incident, IncidentStatus, WorldState


# Keep these costs aligned with movement.py.
BATTERY_DRAIN_PER_MOVE = 0.5
BATTERY_DRAIN_PER_SUPPRESSION_TICK = 0.25
WATER_DRAIN_PER_SUPPRESSION_TICK = 5.0
BATTERY_RESERVE_PCT = 1.0

MAX_PROJECTION_TICKS = 10_000


@dataclass(frozen=True)
class MissionEstimate:
    travel_ticks: int
    suppression_ticks: int
    return_ticks: int
    water_required: float
    battery_required: float
    severity_at_arrival: int
    severity_at_extinguish: int

    @property
    def total_ticks(self) -> int:
        return (
            self.travel_ticks
            + self.suppression_ticks
            + self.return_ticks
        )


def distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Manhattan distance on the simulation grid."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _project_fire_spread(
    severity: int,
    spread_progress: float,
    spread_per_tick: float,
) -> tuple[int, float]:
    """
    Project one spread tick using the same rules as fire_dynamics.py.

    This function doesn't mutate the actual incident.
    """
    if severity >= 5:
        return severity, spread_progress

    spread_progress += spread_per_tick

    while spread_progress >= 1.0 and severity < 5:
        spread_progress -= 1.0
        severity += 1

    return severity, spread_progress


def estimate_mission(
    world: WorldState,
    drone: Drone,
    incident: Incident,
) -> MissionEstimate:
    """
    Estimate resources needed to reach a fire, extinguish it, and return.

    Projects the incident's spread while travelling and suppressing.
    Uses the drone's current position and the incident's current state.
    """
    if incident.status != IncidentStatus.ACTIVE:
        raise ValueError("Cannot estimate a mission for an inactive incident")

    if not 1 <= incident.severity <= 5:
        raise ValueError("Incident severity must be between 1 and 5")

    # The movement code spends one tick to register arrival even when
    # the drone is already at its destination.
    travel_distance = distance(
        (drone.x, drone.y),
        (incident.x, incident.y),
    )
    travel_ticks = max(1, travel_distance)

    return_distance = distance(
        (incident.x, incident.y),
        world.base_position,
    )
    return_ticks = max(1, return_distance)

    severity = incident.severity
    spread_progress = incident.spread_progress

    # Project spread that occurs before the drone arrives.
    for _ in range(travel_ticks):
        severity, spread_progress = _project_fire_spread(
            severity,
            spread_progress,
            incident.spread_per_tick,
        )

    severity_at_arrival = severity
    suppression_progress = incident.suppression_progress
    suppression_ticks = 0

    # Simulate the fire dynamics and suppression tick by tick.
    # advance_world() spreads the fire before applying suppression.
    while suppression_progress < 100.0:
        if suppression_ticks >= MAX_PROJECTION_TICKS:
            raise RuntimeError(
                "Mission projection exceeded the maximum number of ticks"
            )

        severity, spread_progress = _project_fire_spread(
            severity,
            spread_progress,
            incident.spread_per_tick,
        )

        suppression_progress = min(
            100.0,
            suppression_progress + 25.0 / severity,
        )
        suppression_ticks += 1

    water_required = (
        suppression_ticks * WATER_DRAIN_PER_SUPPRESSION_TICK
    )

    battery_required = (
        (travel_ticks + return_ticks) * BATTERY_DRAIN_PER_MOVE
        + suppression_ticks * BATTERY_DRAIN_PER_SUPPRESSION_TICK
        + BATTERY_RESERVE_PCT
    )

    return MissionEstimate(
        travel_ticks=travel_ticks,
        suppression_ticks=suppression_ticks,
        return_ticks=return_ticks,
        water_required=water_required,
        battery_required=battery_required,
        severity_at_arrival=severity_at_arrival,
        severity_at_extinguish=severity,
    )


def can_complete_mission(
    world: WorldState,
    drone: Drone,
    incident: Incident,
) -> bool:
    """Return True only when the drone can afford the estimated mission."""
    estimate = estimate_mission(world, drone, incident)

    return (
        drone.water_pct >= estimate.water_required
        and drone.battery_pct >= estimate.battery_required
    )
