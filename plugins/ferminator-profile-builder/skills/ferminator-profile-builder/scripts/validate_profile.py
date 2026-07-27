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

V1_SCORING = {
    "role_alignment",
    "career_evidence",
    "skills",
    "seniority",
    "geography",
    "compensation",
    "company_preference",
    "freshness",
}
V2_SCORING = {
    "functional_fit",
    "career_evidence",
    "ats_credibility",
    "skills",
    "seniority",
    "opportunity_economics",
    "company_preference",
}
V1_HEADINGS = {
    "## Search thesis",
    "## Strong-fit themes",
    "## Career evidence",
    "## Constraints",
    "## Company preferences",
    "### Prioritize",
    "### Avoid",
    "## Match calibration",
}
V2_HEADINGS = {
    "## Search thesis",
    "## Strong-fit themes",
    "## Career evidence",
    "## Role-family evidence map",
    "## Constraints",
    "## Company preferences",
    "### Prioritize",
    "### Avoid",
    "## Decision calibration",
    "## Unresolved evidence gaps",
}
V2_WRONG_REASONS = {
    "wrong_function",
    "qualification_gap",
    "wrong_seniority",
    "technical_depth",
    "compensation",
    "geography",
    "travel",
    "industry_company",
    "work_style",
    "not_interested",
    "stale_listing",
    "other",
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
    schema_version = root.get("schema_version")
    if schema_version not in {1, 2}:
        errors.append("schema_version must be 1 or 2")

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
    if schema_version == 2:
        for key in (
            "target_base_annual",
            "exceptional_opportunity_floor",
            "minimum_contract_hourly",
        ):
            value = compensation.get(key)
            if value is not None:
                parsed = _number(value, f"search.compensation.{key}", errors)
                if parsed is not None and parsed < 0:
                    errors.append(f"search.compensation.{key} cannot be negative")
        if not isinstance(compensation.get("bonus_equity_can_offset_base"), bool):
            errors.append("search.compensation.bonus_equity_can_offset_base must be boolean")

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
        if schema_version == 2:
            intent = family.get("intent")
            intent_map = {
                "core": ("primary", 50),
                "adjacent": ("adjacent", 55),
                "edge": ("edge", 65),
                "exploratory": ("edge", 40),
            }
            if intent not in intent_map:
                errors.append(f"{path}.intent is invalid")
            elif family.get("tier") != intent_map[intent][0]:
                errors.append(f"{path}.tier conflicts with intent {intent}")
            for key in (
                "must_involve",
                "supporting_evidence",
                "required_signals",
                "false_positive_patterns",
                "disqualifying_responsibilities",
                "acceptable_seniority",
                "tolerated_gaps",
                "non_claims",
            ):
                _string_list(family.get(key), f"{path}.{key}", errors)
            broad_aliases = {"marketing", "ai", "operations", "manager"}
            if broad_aliases & {item.casefold() for item in aliases}:
                errors.append(f"{path}.aliases contains an overly broad standalone alias")
    if len(set(family_ids)) != len(family_ids):
        errors.append("role family ids must be unique")

    for key in ("required_any", "preferred"):
        values = search.get(key)
        if values != []:
            _string_list(values, f"search.{key}", errors)
    exclusions = _mapping(search.get("exclude"), "search.exclude", errors)
    for key, values in exclusions.items():
        _string_list(values, f"search.exclude.{key}", errors)
    if schema_version == 2:
        freshness = _mapping(search.get("freshness"), "search.freshness", errors)
        expected_freshness = {
            "normal_days": 60,
            "older_days": 90,
            "revalidate_after_days": 90,
            "archive_unverified_after_days": 180,
            "default_archive_after_days": 365,
            "preserve_reviewed_and_pipeline": True,
        }
        for key, expected in expected_freshness.items():
            if freshness.get(key) != expected:
                errors.append(f"search.freshness.{key} must be {expected!r}")
        duplicate_policy = _mapping(
            search.get("duplicate_policy"), "search.duplicate_policy", errors
        )
        if duplicate_policy.get("application_suppression_days") != 180:
            errors.append("search.duplicate_policy.application_suppression_days must be 180")
        if duplicate_policy.get("recurrence_scope") not in {"job", "company"}:
            errors.append("search.duplicate_policy.recurrence_scope is invalid")
        if not isinstance(search.get("schedule_preference"), str):
            errors.append("search.schedule_preference is required")
        _string_list(search.get("remote_regions"), "search.remote_regions", errors)
        hybrid_days = search.get("hybrid_max_days_per_week")
        if hybrid_days is not None and (
            not isinstance(hybrid_days, int) or isinstance(hybrid_days, bool)
        ):
            errors.append("search.hybrid_max_days_per_week must be an integer or null")
        if search.get("relocation_willing") is not None and not isinstance(
            search.get("relocation_willing"), bool
        ):
            errors.append("search.relocation_willing must be boolean or null")
        for section in ("company_preferences", "work_patterns"):
            values = _mapping(search.get(section), f"search.{section}", errors)
            if set(values) != {"prefer", "accept", "avoid", "never_show"}:
                errors.append(f"search.{section} must contain four decision levels")
            for key, entries in values.items():
                if entries != []:
                    _string_list(entries, f"search.{section}.{key}", errors)

        decision = _mapping(root.get("decision_model"), "decision_model", errors)
        retrieval = _mapping(decision.get("retrieval"), "decision_model.retrieval", errors)
        _string_list(
            retrieval.get("search_vocabulary"),
            "decision_model.retrieval.search_vocabulary",
            errors,
        )
        eligibility = _mapping(
            decision.get("eligibility"), "decision_model.eligibility", errors
        )
        for key in ("hard_rejections", "manual_review_conditions"):
            _string_list(
                eligibility.get(key), f"decision_model.eligibility.{key}", errors
            )
        desirability = _mapping(
            decision.get("desirability"), "decision_model.desirability", errors
        )
        for key in ("great_if", "maybe_if", "wrong_if"):
            _string_list(
                desirability.get(key), f"decision_model.desirability.{key}", errors
            )
        feedback = _mapping(decision.get("feedback"), "decision_model.feedback", errors)
        reason_codes = set(
            _string_list(
                feedback.get("wrong_reason_codes"),
                "decision_model.feedback.wrong_reason_codes",
                errors,
            )
        )
        if reason_codes != V2_WRONG_REASONS:
            errors.append("decision_model.feedback.wrong_reason_codes is incomplete")
        for key in (
            "capture_great_reason",
            "capture_maybe_tradeoff",
            "capture_wrong_reason",
        ):
            if feedback.get(key) is not True:
                errors.append(f"decision_model.feedback.{key} must be true")

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
    expected_scoring = V2_SCORING if schema_version == 2 else V1_SCORING
    if set(scoring) != expected_scoring:
        errors.append(
            f"scoring must contain exactly the schema-v{schema_version} canonical keys"
        )
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
    required_headings = V2_HEADINGS if schema_version == 2 else V1_HEADINGS
    for heading in sorted(required_headings - present_headings):
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
