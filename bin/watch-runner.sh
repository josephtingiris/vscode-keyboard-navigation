#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# watch-runner.sh — execute a command when a file changes
#
# Summary:
#   Execute a binary or script when a file changes and print a timestamped
#   delimiter before each run. The runner's stdout/stderr are forwarded
#   unchanged to this script's stdout/stderr.
#
# Usage:
#   watch-runner.sh <file-to-watch> <runner-executable>
#
# Examples:
#   ./bin/watch-runner.sh references/keybindings.json \
#       ./bin/keybindings-install-references.sh
#
# Behavior:
#   - Quiet while watching; prints a delimiter line with an ISO UTC
#     datestamp before each runner invocation.
#   - Runner stdout/stderr are passed through to the script's stdout/stderr.
#   - Exits non-zero on missing requirements or invalid arguments.
#
# Requirements:
#   - `realpath`
#   - `inotifywait` (from the `inotify-tools` package)
#
# Exit codes:
#   0   Success
#   1   Signal/interrupt or other runtime error
#   2   Usage / bad args
#
# Author:
#   (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
# -----------------------------------------------------------------------------

set -euo pipefail

WATCH=""
RUNNER=""

aborting() {
    printf '%s\n' "aborting ... ${*}" >&2
    exit 1
}

usage() {
    echo
    echo "usage: ${0##*/} <file-to-watch> <runner-executable>"
    echo
    exit 2
}

validate_requirements() {
    if ! command -v realpath > /dev/null 2>&1; then
        aborting "realpath is required but not found"
    fi
    if ! command -v inotifywait > /dev/null 2>&1; then
        aborting "inotifywait is required; install with: sudo apt install inotify-tools"
    fi
}

main() {
    [ "$#" -ne 2 ] && usage

    WATCH="$1"
    RUNNER="$2"

    validate_requirements

    WATCH_REAL=$(realpath "${WATCH}" 2> /dev/null) || aborting "file not found: ${WATCH}"
    [ ! -f "${WATCH_REAL}" ] && aborting "not a regular file: ${WATCH_REAL}"

    if [[ ${RUNNER} == */* ]]; then
        [ ! -x "${RUNNER}" ] && aborting "runner not executable: ${RUNNER}"
    else
        ! command -v "${RUNNER}" > /dev/null 2>&1 && aborting "runner not found in PATH: ${RUNNER}"
    fi

    # Watch loop: quiet while waiting, print a delimiter then execute runner
    while inotifywait -q -e close_write,modify,move,create "${WATCH_REAL}" > /dev/null 2>&1; do
        echo "---- RUN: $(date -u '+%Y-%m-%dT%H:%M:%SZ') ----"
        "${RUNNER}" "${WATCH_REAL}"
		wait $? || aborting "runner exited with non-zero status"
		sleep 3 # debounce: wait a moment to avoid multiple rapid triggers
    done
}

DIRNAME="$(dirname "$0")"

main "$@"
