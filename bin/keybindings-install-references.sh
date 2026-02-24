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

aborting() {
    printf '\n%s\n\n' "aborting ... ${*}" >&2
    exit 1
}

ansi_echo() {
    local no_newline=0
    if [ "${1:-}" = "-n" ]; then
        no_newline=1
        shift
    fi

    local text="$*"

    if [[ "${text}" == *"${RESET}"* ]]; then
        if [ "${no_newline}" -eq 1 ]; then
            printf "%b" "${text}"
        else
            printf "%b\n" "${text}"
        fi
    else
        if [ "${no_newline}" -eq 1 ]; then
            printf "%b" "${text}${RESET}"
        else
            printf "%b\n" "${text}${RESET}"
        fi
    fi
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
    local keybindings_json

    if [ -f "${1}" ]; then
        keybindings_json="$1"
        shift
    else
        keybindings_json="${DIRNAME}/../references/keybindings.json"
    fi

    [ ! -r "${keybindings_json}" ] && aborting "'${keybindings_json}' file not readable"

    keybindings_json="$(realpath "${keybindings_json}")"

    [ -z "${keybindings_json}" ] && usage

    if [ ! -f "${keybindings_json}" ]; then
        aborting "file '${keybindings_json}' does not exist"
    fi

    validate_json "${keybindings_json}"

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
        ansi_echo "Using provided arguments: ${YELLOW}KEYBINDINGS_SORT_ARGUMENTS='${KEYBINDINGS_SORT_ARGUMENTS}'"
    else
        if [ "${1}" == "1" ]; then
            KEYBINDINGS_SORT_ARGUMENTS="-p key -s when"
            if [ "${2}" == "w" ]; then
                KEYBINDINGS_SORT_ARGUMENTS="-p when -s key"
            fi
        fi

        if [ "${1}" == "2" ]; then
            KEYBINDINGS_SORT_ARGUMENTS="-p key -s when -g positive -w focal-invariant"
            if [ "${2}" == "w" ]; then
                KEYBINDINGS_SORT_ARGUMENTS="-p when -s key -g positive -w focal-invariant"
            fi
        fi

        if [ "${1}" == "3" ]; then
            KEYBINDINGS_SORT_ARGUMENTS="-p key -s when -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled"
            if [ "${2}" == "w" ]; then
                KEYBINDINGS_SORT_ARGUMENTS="-p when -s key -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled"
            fi
        fi

        if [ "${1}" == "4" ]; then
            KEYBINDINGS_SORT_ARGUMENTS="-p key -s when -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters"
            if [ "${2}" == "w" ]; then
                KEYBINDINGS_SORT_ARGUMENTS="-p when -s key -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters"
            fi
        fi

        if [ "${1}" == "5" ]; then
            KEYBINDINGS_SORT_ARGUMENTS="-p key -s when -g positive -w focal-invariant --when-regex config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters,config.keyboardNavigation"
            if [ "${2}" == "w" ]; then
                KEYBINDINGS_SORT_ARGUMENTS="-p when -s key -g positive -w focal-invariant --when-regex config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters,config.keyboardNavigation"
            fi
        fi

        if [ "${1}" == "6" ]; then
            KEYBINDINGS_SORT_ARGUMENTS="-p key -s when"
            if [ "${2}" == "w" ]; then
                KEYBINDINGS_SORT_ARGUMENTS="-p when -s key"
            fi
        fi

        if [ "${1}" == "7" ]; then
            KEYBINDINGS_SORT_ARGUMENTS="-p key -s when"
            if [ "${2}" == "w" ]; then
                KEYBINDINGS_SORT_ARGUMENTS="-p when -s key"
            fi
        fi

        if [ "${KEYBINDINGS_SORT_ARGUMENTS}" == "" ]; then
            # TODO: get, or sync this vale with the Makefile's
            KEYBINDINGS_SORT_ARGUMENTS="-p when -s key -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters"
        fi

        ansi_echo "Using default arguments: ${GREEN}KEYBINDINGS_SORT_ARGUMENTS='${KEYBINDINGS_SORT_ARGUMENTS}'"
    fi
    export KEYBINDINGS_SORT_ARGUMENTS

    echo -n "Sorting JSON '$(basename "${keybindings_json}")' ... "
    if type -p keybindings-sort.py > /dev/null 2>&1; then
        #echo "keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} < \"${keybindings_json}\" > /tmp/keybindings-sorted.json.$$"
        keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} < "${keybindings_json}" > /tmp/keybindings-sorted.json.$$
        #cat /tmp/keybindings-sorted.json.$$
        mv /tmp/keybindings-sorted.json.$$ "${keybindings_json}"
    fi
    echo "OK."

    ansi_echo "Arguments used: ${CYAN}KEYBINDINGS_SORT_ARGUMENTS='${KEYBINDINGS_SORT_ARGUMENTS}'"

    validate_json "${keybindings_json}"

    echo -n "Installing 'references/$(basename "${keybindings_json}")' to '$(vscode_user_home)' ... "
    cp "${keybindings_json}" "${user_keybindings_json}"
    echo "Done."

    #cat "${keybindings_json}"
}

DIRNAME="$(dirname "$0")"

for _arg in "$@"; do
    case "${_arg}" in
        -h | --help)
            usage
            ;;
    esac
done

# ANSI color codes
RESET='\033[0m'
BOLD='\033[1m'
RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
MAGENTA='\033[35m'
CYAN='\033[36m'

main "${@}"
