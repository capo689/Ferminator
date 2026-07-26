#!/usr/bin/env python3
"""Standalone structural validator for Ferminator profile Markdown."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import yaml

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

CANONICAL_SCORING = {
    "role_alignment",
    "career_evidence",
    "skills",
    "seniority",
    "geography",
    "compensation",
    "company_preference",
    "freshness",
}
REQUIRED_HEADINGS = {
    "## Search thesis",
    "## Strong-fit themes",
    "## Career evidence",
    "## Constraints",
    "## Company preferences",
    "### Prioritize",
    "### Avoid",
    "## Match calibration",
}
PLACEHOLDER_PATTERNS = (
    r"\bTODO\b",
    r"\{\{[^}]+\}\}",
    r"\[TODO[^\]]*\]",
    r"\bReplace with\b",
    r"\bfirst-name-last-name\b",
    r"\bFull Name\b",
    r'"00000"',
)


def _mapping(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be a mapping")
        return {}
    return value


def _string_list(value: Any, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"{path} must be a list of non-empty strings")
        return []
    return [item.strip() for item in value]


def _number(value: Any, path: str, errors: list[str]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        errors.append(f"{path} must be a number")
        return None
    return float(value)


def validate_profile_text(raw: str) -> list[str]:
    if yaml is None:
        return [
            "PyYAML is required; install pyyaml in the isolated environment "
            "or run Ferminator's native profile validator"
        ]
    errors: list[str] = []
    if not raw.startswith("---\n"):
        return ["file must start with YAML front matter"]
    try:
        _, front_matter, body = raw.split("---", 2)
    except ValueError:
        return ["file must contain a closing YAML front-matter delimiter"]
    try:
        data = yaml.safe_load(front_matter)
    except yaml.YAMLError as exc:
        return [f"invalid YAML: {exc}"]

    root = _mapping(data, "front matter", errors)
    if root.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    profile = _mapping(root.get("profile"), "profile", errors)
    slug = profile.get("slug")
    if not isinstance(slug, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]{1,62}", slug
    ):
        errors.append("profile.slug must be 2–63 lowercase letters, numbers, or hyphens")
    if not isinstance(profile.get("display_name"), str) or not profile.get(
        "display_name", ""
    ).strip():
        errors.append("profile.display_name is required")
    email_env = profile.get("email_env")
    if email_env is not None and (
        not isinstance(email_env, str)
        or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", email_env)
    ):
        errors.append("profile.email_env must be an environment-variable name")

    search = _mapping(root.get("search"), "search", errors)
    interval = search.get("scan_interval_hours")
    if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 168:
        errors.append("search.scan_interval_hours must be an integer from 1 to 168")
    _string_list(search.get("default_geography"), "search.default_geography", errors)
    if not isinstance(search.get("default_zip"), str) or not re.fullmatch(
        r"\d{5}", search.get("default_zip", "")
    ):
        errors.append("search.default_zip must be a five-digit string")
    if search.get("default_radius_miles") not in {10, 25, 50, 100}:
        errors.append("search.default_radius_miles must be 10, 25, 50, or 100")
    if search.get("default_location_mode") not in {
        "remote",
        "near",
        "remote_or_near",
        "anywhere",
    }:
        errors.append("search.default_location_mode is invalid")

    compensation = _mapping(search.get("compensation"), "search.compensation", errors)
    minimum = compensation.get("minimum_base_annual")
    if minimum is not None:
        parsed_minimum = _number(
            minimum, "search.compensation.minimum_base_annual", errors
        )
        if parsed_minimum is not None and parsed_minimum < 0:
            errors.append("search.compensation.minimum_base_annual cannot be negative")

    _string_list(search.get("employment_types"), "search.employment_types", errors)
    seniority = search.get("target_seniority")
    if seniority != []:
        _string_list(seniority, "search.target_seniority", errors)

    target_titles = _mapping(search.get("target_titles"), "search.target_titles", errors)
    for tier in ("high", "adjacent"):
        titles = target_titles.get(tier)
        if titles != []:
            _string_list(titles, f"search.target_titles.{tier}", errors)

    families = search.get("role_families")
    if not isinstance(families, list) or not families:
        errors.append("search.role_families must contain at least one family")
        families = []
    family_ids: list[str] = []
    for index, raw_family in enumerate(families):
        path = f"search.role_families[{index}]"
        family = _mapping(raw_family, path, errors)
        family_id = family.get("id")
        if not isinstance(family_id, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9-]{1,62}", family_id
        ):
            errors.append(f"{path}.id is invalid")
        else:
            family_ids.append(family_id)
        if not isinstance(family.get("label"), str) or not family.get("label", "").strip():
            errors.append(f"{path}.label is required")
        if family.get("tier") not in {"primary", "adjacent", "edge"}:
            errors.append(f"{path}.tier is invalid")
        threshold = family.get("threshold")
        if (
            not isinstance(threshold, int)
            or isinstance(threshold, bool)
            or not 0 <= threshold <= 100
        ):
            errors.append(f"{path}.threshold must be an integer from 0 to 100")
        aliases = _string_list(family.get("aliases"), f"{path}.aliases", errors)
        if len({item.casefold() for item in aliases}) != len(aliases):
            errors.append(f"{path}.aliases must be unique")
    if len(set(family_ids)) != len(family_ids):
        errors.append("role family ids must be unique")

    for key in ("required_any", "preferred"):
        values = search.get(key)
        if values != []:
            _string_list(values, f"search.{key}", errors)
    exclusions = _mapping(search.get("exclude"), "search.exclude", errors)
    for key, values in exclusions.items():
        _string_list(values, f"search.exclude.{key}", errors)

    notifications = _mapping(root.get("notifications"), "notifications", errors)
    review = _number(
        notifications.get("review_minimum_score"),
        "notifications.review_minimum_score",
        errors,
    )
    minimum_score = _number(
        notifications.get("minimum_score"), "notifications.minimum_score", errors
    )
    exceptional = _number(
        notifications.get("exceptional_score"),
        "notifications.exceptional_score",
        errors,
    )
    if review is not None and minimum_score is not None and review >= minimum_score:
        errors.append("review_minimum_score must be lower than minimum_score")
    if (
        minimum_score is not None
        and exceptional is not None
        and exceptional < minimum_score
    ):
        errors.append("exceptional_score must be at least minimum_score")

    scoring = _mapping(root.get("scoring"), "scoring", errors)
    if set(scoring) != CANONICAL_SCORING:
        errors.append("scoring must contain exactly the eight canonical keys")
    weights = [
        parsed
        for key, value in scoring.items()
        if (parsed := _number(value, f"scoring.{key}", errors)) is not None
    ]
    if any(weight < 0 for weight in weights):
        errors.append("scoring weights cannot be negative")
    if weights and abs(sum(weights) - 100) > 0.01:
        errors.append(f"scoring weights must total 100, got {sum(weights):g}")

    stripped_body = body.strip()
    if len(stripped_body) < 500:
        errors.append("profile body is too short to support useful matching")
    if not re.search(r"^# .+ — Career Search Profile$", stripped_body, re.MULTILINE):
        errors.append("profile body requires '# Full Name — Career Search Profile'")
    present_headings = set(re.findall(r"^#{2,3} .+$", stripped_body, re.MULTILINE))
    for heading in sorted(REQUIRED_HEADINGS - present_headings):
        errors.append(f"missing body heading: {heading}")
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, raw, re.IGNORECASE):
            errors.append(f"unresolved placeholder matches: {pattern}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    try:
        raw = args.profile.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    errors = validate_profile_text(raw)
    if errors:
        print("INVALID", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"VALID: {args.profile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
