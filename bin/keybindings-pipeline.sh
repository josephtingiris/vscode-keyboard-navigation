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
    export VSCODE_KEYBINDINGS_BIN_DIR="$(realpath "${0%/*}")"

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

    if [ ! -d "${VSCODE_KEYBINDINGS_TMP_DIR}" ]; then
        mkdir -p "${VSCODE_KEYBINDINGS_TMP_DIR}"
    fi

    if [ ! -d "${VSCODE_KEYBINDINGS_TMP_DIR}" ]; then
        aborting "'${VSCODE_KEYBINDINGS_TMP_DIR}' directory not found"
    fi

    if [ ! -w "${VSCODE_KEYBINDINGS_TMP_DIR}" ]; then
        aborting "'${VSCODE_KEYBINDINGS_TMP_DIR}' directory not found writable"
    fi

    echo

    if [ "$(type -t "${1}" 2>&1 | grep ^function$)" == 'function' ]; then
        ${@}
    else
        type -t "${1}"
        aborting "unknown command: ${1}"
    fi
}

# add the canonical diagnostic surfaces into the references keybindings.json test surface, preserving the original base objects and their placements
references_test_surface_diagnostics_add() {
    local tmp_file="${VSCODE_KEYBINDINGS_TMP_DIR}/m1.$$.jsonc"

    local test_surface="${VSCODE_KEYBINDINGS_REFERENCES_DIR}/keybindings.json"

    local diagnostic_surface diagnostic_surfaces=()

    diagnostic_surfaces+=("${VSCODE_KEYBINDINGS_REFERENCES_DIR}/keybindings.surface.jsonc")
    diagnostic_surfaces+=("${VSCODE_KEYBINDINGS_REFERENCES_DIR}/keybindings.surface.vi.jsonc")

    echo tmp_file=${tmp_file}
    echo

    for diagnostic_surface in "${diagnostic_surfaces[@]}"; do
        echo "----"
        echo "diagnostic_surface=${diagnostic_surface}"
        echo

        keybindings-merge.py --prefer left --base left --out "${tmp_file}" "${test_surface}" "${diagnostic_surface}"
        cat "${tmp_file}" | keybindings-sort.py -w focal-invariant > "${test_surface}"
        echo

        rm -f "${tmp_file}" &> /dev/null
    done

    echo "Updating corpus comments ..."
    keybindings-corpus.py --comments "${test_surface}" > "${tmp_file}"
    cat "${tmp_file}" | keybindings-sort.py -w focal-invariant > "${test_surface}"
    echo

    echo "Annotating duplicates ..."
    keybindings-duplicate.py --detect "${test_surface}" > "${tmp_file}"
    cat "${tmp_file}" | keybindings-sort.py -w focal-invariant > "${test_surface}"

    if type -P prettier &> /dev/null; then
        echo
        echo "Making ${test_surface} prettier ..."
        prettier "${test_surface}" > "${tmp_file}"
        cat "${tmp_file}" | keybindings-sort.py -w focal-invariant > "${test_surface}"
        rm -f "${tmp_file}" &> /dev/null
    fi

    rm -f "${tmp_file}" &> /dev/null
    echo
}

references_test_surface_diagnostics_build() {
    local tmp_file="${VSCODE_KEYBINDINGS_TMP_DIR}/m1.$$.jsonc"

    local test_surface="${VSCODE_KEYBINDINGS_REFERENCES_DIR}/keybindings.json"

    local here="${PWD}"

    cd "${VSCODE_KEYBINDINGS_DIR}"}

    make corpora
    make maps
    make surfaces

    keybindings-pipeline.sh references_test_surface_diagnostics_remove
    keybindings-pipeline.sh references_test_surface_diagnostics_add

    cd "${here}"
}

references_test_surface_diagnostics_expand() {
    local tmp_file="${VSCODE_KEYBINDINGS_TMP_DIR}/m1.$$.jsonc"

    echo tmp_file=${tmp_file}
}

# remove all canonical diagnostic command objects from the references keybinding.json test surface, leaving only the valid command objects
references_test_surface_diagnostics_remove() {
    local tmp_file="${VSCODE_KEYBINDINGS_TMP_DIR}/m1.$$.jsonc"

    local test_surface="${VSCODE_KEYBINDINGS_REFERENCES_DIR}/keybindings.json"

    echo tmp_file=${tmp_file}
    echo

    echo "Removing diagnosticts from ${test_surface} ..."
    cat "${test_surface}" | keybindings-remove-objects.py command '+' > "${tmp_file}"
    cat "${tmp_file}" | keybindings-sort.py -w focal-invariant > "${test_surface}"
    rm -f "${tmp_file}" &> /dev/null
}

# ingest (merge) an existing keybindings.json array into the references keybindings.json test surface, overwriting existing objects
references_test_surface_ingest() {
    local tmp_file="${VSCODE_KEYBINDINGS_TMP_DIR}/m1.$$.jsonc"

    echo tmp_file=${tmp_file}
}

references_test_surface_foci_get() {
    local tmp_file="${VSCODE_KEYBINDINGS_TMP_DIR}/m1.$$.jsonc"

    local test_surface="${VSCODE_KEYBINDINGS_REFERENCES_DIR}/keybindings.json"

    echo test_surface=${test_surface}, tmp_file=${tmp_file}

    grep \"when\": "${test_surface}" |
        sed -E \
            -e 's/.*"when": "([^"]*)".*/\1/' \
            -e "/config.keyboardNavigation.enabled/s///g" \
            -e "/config.keyboardNavigation.keys.letters == 'emacs'/s///g" \
            -e "/config.keyboardNavigation.keys.letters == 'kbm'/s///g" \
            -e "/config.keyboardNavigation.keys.letters == 'vi'/s///g" \
            -e "/config.keyboardNavigation.keys.arrows/s///g" \
            -e "/config.keyboardNavigation.juke.enabled/s///g" \
            -e "/config.keyboardNavigation.split.enabled/s///g" \
            -e "/config.keyboardNavigation.terminal.enabled/s///g" \
            -e "/config.keyboardNavigation.chords.action/s///g" \
            -e "/config.keyboardNavigation.chords.debug/s///g" \
            -e "/config.workbench.sideBar.location == 'bottom'/s///g" \
            -e "/config.workbench.sideBar.location == 'left'/s///g" \
            -e "/config.workbench.sideBar.location == 'right'/s///g" \
            -e "/config.workbench.sideBar.location == 'top'/s///g" \
            -e "/panelPosition == 'bottom'/s///g" \
            -e "/panelPosition == 'left'/s///g" \
            -e "/panelPosition == 'right'/s///g" \
            -e "/panelPosition == 'top'/s///g" \
            -e '/&&/s//@@/g' \
            -e '/  */s// /g' \
            -e '/^  */s///g' \
            -e 's/[[:blank:]]*$//' |
        sed \
            -e '/@@ @@ @@/s//@@/g' \
            -e '/@@ @@/s//@@/g' \
            -e '/^@@ /s///g' \
            -e '/ @@$/s///g' \
            -e '/^@@$/s///g' \
            -e '/@@/s//\&\&/g' \
            -e 's/[[:blank:]]*$//' |
        sort -u | grep '!'

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
