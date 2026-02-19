#!/usr/bin/env bash
#
#  (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
#
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
#   while true; do KEYBINDINGS_SORT_ARGUMENTS="-p when" ./bin/watch-runner.sh ./references/keybindings.json ./bin/keybindings-install-references.sh; sleep 3; done
#   while true; do KEYBINDINGS_SORT_ARGUMENTS="-p key -s when" ./bin/watch-runner.sh ./references/keybindings.json ./bin/keybindings-install-references.sh; sleep 3; done
#   while true; do KEYBINDINGS_SORT_ARGUMENTS="-p when -w focal-invariant -g positive" ./bin/watch-runner.sh ./references/keybindings.json ./bin/keybindings-install-references.sh; sleep 3; done
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
#   1   Validation / runtime error
#   2   Usage / bad args
# -----------------------------------------------------------------------------

KEYBINDINGS_JSON=""

aborting() {
    printf '\n%s\n\n' "aborting ... ${*}" >&2
    exit 1
}

usage() {
    echo
    echo "usage: ${0##*/} [-h|--help] [keybindings.json]"
    echo
    exit 2
}

validate_json() {
    local file="${1}"
    local rc=0
    local tempfile="/tmp/$(basename "${file}").nocomments.json.$$"

    cat "${file}" | keybindings-remove-comments.py > "${tempfile}"
    echo >> "${tempfile}" # ensure file ends with newline for jq
    echo -n "Validating JSON '$(basename "${file}")' ... "
    if ! jq . "${tempfile}" > /dev/null 2>&1; then
        jq . "${tempfile}"
        rm -f "${tempfile}" &> /dev/null
        aborting "'${tempfile}' is not valid JSON"
    fi
    rm -f "${tempfile}" &> /dev/null
    echo "OK."

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
	if [ -d "${VSCODE_USER_DIR}" ]; then
    	user_keybindings_json="${VSCODE_USER_DIR}/keybindings.json"
	else
    	user_keybindings_json="$(vscode_user_home)/AppData/Roaming/Code/User/keybindings.json"
	fi
    if [ ! -r "${user_keybindings_json}" ]; then
        aborting "'${user_keybindings_json}' file not found readable"
    fi

    if [ "${KEYBINDINGS_SORT_ARGUMENTS}" ]; then
        echo "Using provided KEYBINDINGS_SORT_ARGUMENTS='${KEYBINDINGS_SORT_ARGUMENTS}'"
    else
        KEYBINDINGS_SORT_ARGUMENTS="-p key -s when"
        KEYBINDINGS_SORT_ARGUMENTS="-p when -s key -g positive -w focal-invariant"
        KEYBINDINGS_SORT_ARGUMENTS="-p when -s key -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled"
        KEYBINDINGS_SORT_ARGUMENTS="-p key -s when -g positive -w focal-invariant"
        KEYBINDINGS_SORT_ARGUMENTS="-p key -s when -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters"
        echo "Using default KEYBINDINGS_SORT_ARGUMENTS='${KEYBINDINGS_SORT_ARGUMENTS}'"
    fi
    export KEYBINDINGS_SORT_ARGUMENTS

    echo -n "Sorting JSON '$(basename "${KEYBINDINGS_JSON}")' ... "
    if type -p keybindings-sort.py > /dev/null 2>&1; then
        #echo "keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} < \"${KEYBINDINGS_JSON}\" > /tmp/keybindings-sorted.json.$$"
        keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} < "${KEYBINDINGS_JSON}" > /tmp/keybindings-sorted.json.$$
        #cat /tmp/keybindings-sorted.json.$$
        mv /tmp/keybindings-sorted.json.$$ "${KEYBINDINGS_JSON}"
    fi
    echo "OK."

    validate_json "${KEYBINDINGS_JSON}"

    echo -n "Installing 'references/$(basename "${KEYBINDINGS_JSON}")' to '$(vscode_user_home)' ... "
    cp "${KEYBINDINGS_JSON}" "${user_keybindings_json}"
    echo "Done."

    #cat "${KEYBINDINGS_JSON}"
}

DIRNAME="$(dirname "$0")"

for _arg in "$@"; do
    case "${_arg}" in
        -h|--help)
            usage
            ;;
    esac
done

[ "$#" -lt 1 ] && KEYBINDINGS_JSON="${DIRNAME}/../references/keybindings.json" || KEYBINDINGS_JSON="$1"
[ ! -r "${KEYBINDINGS_JSON}" ] && aborting "'${KEYBINDINGS_JSON}' file not readable"
KEYBINDINGS_JSON="$(realpath "${KEYBINDINGS_JSON}")"

main "${KEYBINDINGS_JSON}"
