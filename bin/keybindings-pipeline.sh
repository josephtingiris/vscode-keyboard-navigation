#!/usr/bin/env bash
#
# (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
#
# keybindings pipelines
#

# globals (exports)

# functions

aborting() {
    echo
    echo "aborting ... ${@}"
    echo
    exit 1
}

main() {
    export VSCODE_KEYBINDINGS_BIN_DIR="${0%/*}"

    if [ -d "${VSCODE_KEYBINDINGS_BIN_DIR}"/../references ]; then
        export VSCODE_KEYBINDINGS_DIR="${VSCODE_KEYBINDINGS_BIN_DIR%/*}"
        export VSCODE_KEYBINDINGS_REFERENCES_DIR="${VSCODE_KEYBINDINGS_DIR}/references"
        export VSCODE_KEYBINDINGS_TMP_DIR="${VSCODE_KEYBINDINGS_DIR}/tmp"
    fi

    [ "${VSCODE_KEYBINDINGS_DIR}" == "" ] && aborting "could not determine VSCODE_KEYBINDINGS_DIR"

    echo "VSCODE_KEYBINDINGS_DIR=${VSCODE_KEYBINDINGS_DIR}"
    echo "VSCODE_KEYBINDINGS_BIN_DIR=${VSCODE_KEYBINDINGS_BIN_DIR}"
    echo "VSCODE_KEYBINDINGS_REFERENCES_DIR=${VSCODE_KEYBINDINGS_REFERENCES_DIR}"
    echo "VSCODE_KEYBINDINGS_TMP_DIR=${VSCODE_KEYBINDINGS_TMP_DIR}"

    export PATH="${PATH}:${VSCODE_KEYBINDINGS_BIN_DIR}"

    if [ "${1}" == "" ]; then
        usage
    fi

    echo

    if type -t "${1}" > /dev/null 2>&1; then
        "${@}"
    else
        aborting "unknown command: ${1}"
    fi
}

# merge (force) an existing keybindings.json into the test surface, overwriting existing objects
pipeline_references_keybindings_json_test_surface_ingest() {
    echo rm -f m1.jsonc
}

# merge the canonical diagnostic surfaces into a single 'max' (very large) test surface, preserving the original base objects and their original placements
pipeline_references_keybindings_json_test_surface_max() {
    echo keybindings-merge.py --prefer left --base left --out m1.jsonc ${VSCODE_KEYBINDINGS_REFERENCES_DIR}/keybindings.json ${VSCODE_KEYBINDINGS_REFERENCES_DIR}/keybindings.surface.vi.jsonc
    echo keybindings-sort.py -w focal-invariant #< m1.jsonc > ${VSCODE_KEYBINDINGS_REFERENCES_DIR}/keybindings.json
    echo rm -f m1.jsonc
}

# remove all uniq diagnostic command objects from the test surface, leaving only the 'min' (very few) valid ones
pipeline_references_keybindings_json_test_surface_min() {
    echo rm -f m1.jsonc
}

usage() {
    printf "\nusage: $(basename "$0") <option>\n\n"

    echo "options:"
    echo
    echo " - KEYBINDINGS_MAP_FOCUS"
    echo

    #echo "examples:"
    #echo
    #echo "KEYBINDINGS_MAP_FOCUS=\"inQuickEdit && editorFocus\" $(basename $0) vi"
    #echo "KEYBINDINGS_MAP_MODIFIERS=shift+alt KEYBINDINGS_MAP_FOCUS=\"inQuickEdit\" $(basename $0) vi"
    #echo "WHEN_PREFIX=\"config.keyboardNavigation.enabled && config.keyboardNavigation.keys.letters == 'vi'\" KEYBINDINGS_MAP_MODIFIERS=alt,shift+alt KEYBINDINGS_MAP_FOCUS=\"inQuickEdit\" $(basename $0) vi"
    #echo

    exit 99
}

# main

[ "${0}" != "${BASH_SOURCE}" ] && return # if it was sourced

# execute

[ "${1}" == "" ] && usage

main ${@}
