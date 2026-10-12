from dataclasses import dataclass, field
from enum import Enum


class DroneStatus(str, Enum):
    IDLE = "idle"
    EN_ROUTE = "en_route"
    SUPPRESSING = "suppressing"
    RETURNING = "returning"
    REFILLING = "refilling"


class IncidentStatus(str, Enum):
    ACTIVE = "active"
    CONTROLLED = "controlled"
    EXTINGUISHED = "extinguished"


@dataclass
class Drone:
    drone_id: str
    x: int
    y: int
    battery_pct: float = 100.0
    water_pct: float = 100.0
    status: DroneStatus = DroneStatus.IDLE
    target_incident_id: str | None = None


@dataclass
class Incident:
    incident_id: str
    x: int
    y: int
    severity: int = 1       # 1 = minor, 5 = critical
    spread_per_tick: float = 0.1
    status: IncidentStatus = IncidentStatus.ACTIVE
    created_tick: int = 0


@dataclass
class WorldState:
    width: int = 20
    height: int = 14
    base_position: tuple[int, int] = (10, 13)
    tick: int = 0
    drones: dict[str, Drone] = field(default_factory=dict)
    incidents: dict[str, Incident] = field(default_factory=dict)
    event_log: list[str] = field(default_factory=list)