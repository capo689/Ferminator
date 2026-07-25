#!/usr/bin/env bash
# Install the daily fetch cron job for anthropic-tracker.
#
# Idempotent: re-running this won't duplicate the line. The line is
# tagged with the marker '# anthropic-tracker' so this script can find
# and replace it cleanly.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${HOME}/logs"
LOG_FILE="${LOG_DIR}/anthropic-tracker.log"
MARKER="# anthropic-tracker"
SCHEDULE="${SCHEDULE:-0 10 * * *}"   # default 10:00 UTC = 06:00 ET

mkdir -p "${LOG_DIR}"

# Verify docker compose is reachable
if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is not installed or not on PATH" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "error: 'docker compose' (v2) is not available" >&2
  exit 1
fi

# Verify the compose file is at the expected path
if [[ ! -f "${REPO_DIR}/docker-compose.yml" ]]; then
  echo "error: ${REPO_DIR}/docker-compose.yml not found" >&2
  exit 1
fi

NEW_LINE="${SCHEDULE} cd ${REPO_DIR} && docker compose run --rm tracker-fetch >> ${LOG_FILE} 2>&1 ${MARKER}"

# Pull existing crontab (or empty if none), strip any prior anthropic-tracker
# entries, append the new one.
{
  crontab -l 2>/dev/null | grep -v "${MARKER}" || true
  echo "${NEW_LINE}"
} | crontab -

echo "Installed cron entry:"
echo "  ${NEW_LINE}"
echo
echo "Logs: ${LOG_FILE}"
echo "Verify with: crontab -l | grep anthropic-tracker"
echo "Remove with: crontab -l | grep -v '${MARKER}' | crontab -"
