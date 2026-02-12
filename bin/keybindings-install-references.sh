#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# keybindings-install-references.sh — install `references/keybindings.json` into VS Code
#
# Summary:
#   Validate and copy a project's `references/keybindings.json` into the user's
#   VS Code keybindings location (detects WSL vs native Windows). Optionally
#   sorts and validates the file before installation.
#
# Usage:
#   keybindings-install-references.sh [keybindings.json]
#
# Examples:
#   ./bin/keybindings-install-references.sh references/keybindings.json
#   ./bin/keybindings-install-references.sh references/keybindings.json
#   while true; do ./bin/watch-runner.sh ./references/keybindings.json ./bin/keybindings-install-references.sh; sleep 3; done

#
# Behavior:
#   - Validates JSONC using `keybindings-remove-comments.py | jq` before installing.
#   - If `keybindings-sort.py` is available, sorts the keybindings before copying.
#   - Detects WSL vs native Windows to compute the target user profile path.
#   - Copies the provided file to the VS Code user keybindings location.
#
# Requirements:
#   - `realpath`, `jq` and `keybindings-remove-comments.py` available in PATH
#
# Exit codes:
#   0   Success
#   1   Usage / bad args
#   2   Validation / runtime error
#
# Author:
#   (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
# -----------------------------------------------------------------------------

KEYBINDINGS_JSON=""

aborting() {
    printf '\n%s\n\n' "aborting ... ${*}" >&2
    exit 1
}

usage() {
    echo
    echo "usage: ${0##*/} [keybindings.json]"
    echo
    exit 99
}

validate_json() {
    local file="${1}"
    local rc=0
	
    if ! cat "${file}" | keybindings-remove-comments.py | jq . > /dev/null 2>&1; then
        aborting "'${file}' is not valid JSON"
    fi
}

vscode_user_home() {
    local vscode_home=""
    if [ -n "${WSL_DISTRO_NAME}" ]; then
        vscode_home=$(which wslconfig.exe 2> /dev/null | grep AppData | awk -F\/AppData '{print $1}')
    else
        vscode_home="${HOME}"
    fi
    echo "${vscode_home}"
}

main() {
    [ -z "${1}" ] && usage

    KEYBINDINGS_JSON="${1}"

    if [ ! -f "${KEYBINDINGS_JSON}" ]; then
        aborting "file '${KEYBINDINGS_JSON}' does not exist"
    fi

    validate_json "${KEYBINDINGS_JSON}"

    local user_keybindings_json
    user_keybindings_json="$(vscode_user_home)/AppData/Roaming/Code/User/keybindings.json"
    if [ ! -r "${user_keybindings_json}" ]; then
        aborting "'${user_keybindings_json}' file not found readable"
    fi

	KEYBINDINGS_SORT_ARGUMENTS="${KEYBINDINGS_SORT_ARGUMENTS:--p key -s when}"
    if type -p keybindings-sort.py > /dev/null 2>&1; then
        keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} < "${KEYBINDINGS_JSON}" > /tmp/keybindings-sorted.json
        mv /tmp/keybindings-sorted.json "${KEYBINDINGS_JSON}"
    fi

    echo -n "Installing 'references/$(basename "${KEYBINDINGS_JSON}")' to '$(vscode_user_home)' ... "
    cp "${KEYBINDINGS_JSON}" "${user_keybindings_json}"
    echo "Done."

    #cat "${KEYBINDINGS_JSON}"
}

DIRNAME="$(dirname "$0")"

[ "$#" -lt 1 ] && KEYBINDINGS_JSON="${DIRNAME}/../references/keybindings.json" || KEYBINDINGS_JSON="$1"
[ ! -r "${KEYBINDINGS_JSON}" ] && aborting "'${KEYBINDINGS_JSON}' file not readable"
KEYBINDINGS_JSON="$(realpath "${KEYBINDINGS_JSON}")"

main "${KEYBINDINGS_JSON}"
