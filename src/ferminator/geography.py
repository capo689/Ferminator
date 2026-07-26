"""Offline United States postal geography and job-location classification."""

from __future__ import annotations

import csv
import math
import re
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATASET = Path(__file__).resolve().parent / "data" / "geonames-us-postal.zip"


@dataclass(frozen=True)
class PostalPlace:
    zip_code: str
    city: str
    state: str
    latitude: float
    longitude: float


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


@lru_cache(maxsize=1)
def postal_index() -> tuple[dict[str, PostalPlace], dict[tuple[str, str], PostalPlace]]:
    by_zip: dict[str, PostalPlace] = {}
    by_city_state: dict[tuple[str, str], PostalPlace] = {}
    with zipfile.ZipFile(DATASET) as archive, archive.open("US.txt") as source:
        rows = csv.reader((line.decode("utf-8") for line in source), delimiter="\t")
        for row in rows:
            if len(row) < 11 or not row[9] or not row[10]:
                continue
            place = PostalPlace(row[1], row[2], row[4], float(row[9]), float(row[10]))
            by_zip.setdefault(place.zip_code, place)
            by_city_state.setdefault((_key(place.city), place.state.casefold()), place)
    return by_zip, by_city_state


def lookup_zip(zip_code: str) -> PostalPlace | None:
    return postal_index()[0].get(zip_code.strip())


def coordinates_for_label(label: str) -> PostalPlace | None:
    """Resolve a ZIP or common City, ST label without a network lookup."""
    if not label:
        return None
    zip_match = re.search(r"\b(\d{5})(?:-\d{4})?\b", label)
    if zip_match:
        return lookup_zip(zip_match.group(1))
    _, cities = postal_index()
    pieces = [piece.strip() for piece in re.split(r"[,|;/•]", label) if piece.strip()]
    for index, piece in enumerate(pieces[:-1]):
        state_match = re.match(r"^([A-Za-z]{2})(?:\b|$)", pieces[index + 1])
        if state_match:
            found = cities.get((_key(piece), state_match.group(1).casefold()))
            if found:
                return found
    compact = re.search(r"\b([A-Za-z .'-]+),?\s+([A-Z]{2})\b", label)
    if compact:
        return cities.get((_key(compact.group(1)), compact.group(2).casefold()))
    return None


def distance_miles(origin: PostalPlace, destination: PostalPlace) -> float:
    radius = 3958.7613
    lat1, lat2 = math.radians(origin.latitude), math.radians(destination.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(destination.longitude - origin.longitude)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def job_distance_miles(job: dict, origin: PostalPlace) -> float | None:
    distances = []
    for location in job.get("locations") or [{"label": job.get("location", "")}]:
        place = coordinates_for_label(location.get("label", ""))
        if place:
            distances.append(distance_miles(origin, place))
    return min(distances) if distances else None


def is_remote_job(job: dict) -> bool:
    if str(job.get("workplace", "")).casefold() == "remote":
        return True
    return any(location.get("is_remote") for location in job.get("locations") or [])


def location_category(job: dict, distance: float | None, radius: int) -> tuple[str, str]:
    remote = is_remote_job(job)
    label = " ".join(
        location.get("label", "") for location in job.get("locations") or []
    ) or str(job.get("location", ""))
    restricted = bool(
        re.search(
            r"\b(?:within|only|must reside|eligible states?|time zones?|region(?:al)?)\b",
            label,
            re.I,
        )
    )
    if remote:
        return (
            ("remote_regional", "Remote — regional restriction")
            if restricted
            else ("remote_us", "Remote — United States")
        )
    if distance is not None and distance <= radius:
        workplace = str(job.get("workplace", "")).casefold()
        if workplace == "hybrid":
            return "hybrid_local", "Hybrid/local"
        return "onsite_local", "On-site/local"
    return "location_unknown", "Location outside radius or unknown"
