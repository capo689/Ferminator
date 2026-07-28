"""Guards for the unrated-jobs export.

The export is only useful if its idea of "on Discover" matches the page's. It
did not: the page filters by location mode, the export did not, and the result
was an export roughly four times the size of the real feed, full of on-site
roles outside the user's radius that the page will never show.
"""

from __future__ import annotations

import ast
from pathlib import Path

SCRIPT = Path("scripts/export_unrated_discover_xml.py")


def _collect_function(name: str) -> ast.FunctionDef:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {SCRIPT}")


def _calls_in(node: ast.AST) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def test_export_applies_the_pages_location_filter() -> None:
    """Regression: an export of "all unrated jobs on Discover" listed 319 when
    the page showed 58, because location mode was never applied."""
    calls = _calls_in(_collect_function("_discover_matches"))

    assert "apply_default_discover_filters" in calls, (
        "the export must apply the same location-mode filter as /discover, "
        "or it reports jobs the page will never show"
    )


def test_location_filter_is_not_scoped_away() -> None:
    """Location is a hard constraint, so no scope may skip it.

    Role thresholds and freshness are visibility preferences and may vary by
    scope. Being unable to reach the office is not a preference.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    body = source.split("def _discover_matches", 1)[1].split("\ndef ", 1)[0]

    location_line = next(
        index
        for index, line in enumerate(body.splitlines())
        if "apply_default_discover_filters(" in line
    )
    guards = [
        index
        for index, line in enumerate(body.splitlines())
        if line.strip().startswith('if scope ==')
    ]

    assert all(guard > location_line for guard in guards), (
        "apply_default_discover_filters must run before any scope guard, "
        "so every scope inherits the location constraint"
    )


def test_both_scopes_are_declared() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"discover"' in source and '"all-eligible"' in source
