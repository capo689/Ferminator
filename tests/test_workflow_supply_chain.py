"""Supply-chain and injection guards for the GitHub Actions workflows.

These are static checks over the workflow files. They exist because both classes
of problem are invisible in review: a floating action tag looks identical to a
pinned one at a glance, and an interpolated dispatch input looks like an
ordinary shell variable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted(Path(".github/workflows").glob("*.yml"))

# `uses: owner/repo@ref` with an optional trailing comment.
USES = re.compile(r"^\s*-?\s*uses:\s*(?P<action>[^@\s]+)@(?P<ref>\S+)(?:\s*#\s*(?P<version>\S+))?")

# Only inputs and event payload fields are attacker-controlled. matrix, job,
# and secrets contexts are authored in the workflow itself.
UNTRUSTED = re.compile(r"\$\{\{\s*(?:inputs\.|github\.event\.(?!name\b))")


def test_workflows_exist() -> None:
    """Guard against the glob silently matching nothing."""
    assert len(WORKFLOWS) >= 4, f"expected the workflow set, found {WORKFLOWS}"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_pinned_to_a_full_commit_sha(workflow: Path) -> None:
    """A floating tag lets the action's owner change what runs in CI.

    These workflows hold the production database URL, so an action resolving to
    new code without any change here is the whole supply-chain risk. Local
    actions (./...) and Docker refs are out of scope.
    """
    unpinned = []
    for number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), 1):
        match = USES.match(line)
        if not match or match["action"].startswith((".", "docker://")):
            continue
        ref = match["ref"]
        if not re.fullmatch(r"[0-9a-f]{40}", ref):
            unpinned.append(f"{workflow.name}:{number} {match['action']}@{ref}")

    assert not unpinned, "actions must be pinned to a full commit SHA: " + ", ".join(unpinned)


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_pinned_actions_record_the_version_they_pin(workflow: Path) -> None:
    """A bare SHA is unreadable and never gets updated. Keep the tag beside it."""
    missing = []
    for number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), 1):
        match = USES.match(line)
        if not match or match["action"].startswith((".", "docker://")):
            continue
        if re.fullmatch(r"[0-9a-f]{40}", match["ref"]) and not match["version"]:
            missing.append(f"{workflow.name}:{number} {match['action']}")

    assert not missing, "pinned actions need a trailing version comment: " + ", ".join(missing)


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_untrusted_input_never_reaches_a_run_block(workflow: Path) -> None:
    """Regression: `ferminator rescore --slug "${{ inputs.slug }}"`.

    GitHub pastes the expression into the script before bash parses it, so a
    slug carrying shell syntax executes rather than being passed as an
    argument. Dispatch inputs have to arrive through `env:` and be referenced
    as ordinary shell variables, which bash then treats as data.
    """
    lines = workflow.read_text(encoding="utf-8").splitlines()
    offenders: list[str] = []
    in_run = False
    run_indent = 0

    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())

        if in_run and indent <= run_indent:
            in_run = False
        if re.match(r"^\s*-?\s*run:\s*\|?", line) and not stripped.startswith("#"):
            in_run = True
            run_indent = indent
            if UNTRUSTED.search(line):
                offenders.append(f"{workflow.name}:{number} {stripped}")
            continue
        if in_run and UNTRUSTED.search(line):
            offenders.append(f"{workflow.name}:{number} {stripped}")

    assert not offenders, (
        "untrusted input interpolated into a shell script; pass it through env: instead: "
        + ", ".join(offenders)
    )
