"""Location checks. Coordinates come from the voter's device, so they are evidence, not proof:
the IP address is stored next to them so the two can be compared in the forensic report."""
import math

from . import config
from .errors import ServiceError


def valid(lat, lng) -> bool:
    return (isinstance(lat, (int, float)) and isinstance(lng, (int, float))
            and -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0 and lng == 0))


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in metres."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geofence_enabled() -> bool:
    return config.GEOFENCE_RADIUS_M > 0


def distance_from_center(lat, lng) -> float | None:
    if not geofence_enabled() or not valid(lat, lng):
        return None
    return round(distance_m(lat, lng, config.GEOFENCE_LAT, config.GEOFENCE_LNG), 1)


def require_location(lat, lng):
    """Raise ServiceError if location is mandatory and missing, or outside the optional geofence."""
    if not valid(lat, lng):
        if config.LOCATION_REQUIRED:
            raise ServiceError("Turn on location services and allow access to continue.", 400)
        return
    d = distance_from_center(lat, lng)
    if d is not None and d > config.GEOFENCE_RADIUS_M:
        raise ServiceError("You appear to be outside the voting area.", 403)
