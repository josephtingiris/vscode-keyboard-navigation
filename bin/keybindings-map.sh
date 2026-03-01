#!/usr/bin/env bash
#
# (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
#
# generate keybindings 'maps'
#

# globals (exports)

# authoritative defaults; these are exported as shell-escaped scalar strings (below)
#
A_KEYBINDINGS_MAP_FOCI=(auxiliaryBarFocus editorFocus 'editorFocus && editorTextFocus' 'editorFocus && panelFocus' panelFocus 'panelFocus && sideBarFocus' 'panelFocus && terminalFocus' statusBarFocused terminalFocus)
A_KEYBINDINGS_MAP_PANEL_POSITIONS=(top bottom left right)
A_KEYBINDINGS_MAP_SIDEBAR_LOCATIONS=(left right)

export KEYBINDINGS_MAP_MODIFIERS="alt,shift+alt,ctrl+alt,ctrl+alt+meta,ctrl+shift+alt"

# functions

keybindings_map() {
    local make_mode=0
    # parse optional flags (only --make for now)
    while [ "${1:-}" != "" ] && [[ "${1}" == --* ]]; do
        case "${1}" in
            --make)
                make_mode=1
                shift
                ;;
            *)
                break
                ;;
        esac
    done

    [ "${1}" == "" ] && printf "\nusage: keybindings_map [--make] <lang|none>\n\n" && return 1

    local keybindings_map_lang keybindings_map_langs="${1//,/ }"

    [ "${keybindings_map_langs}" == 'none' ] && keybindings_map_langs=''

    local epoch="$(date +%s)"

    local map_file="keybindings_map.${epoch}"

    local when_prefix="config.keyboardNavigation.enabled"

    local pp fl fc

    for keybindings_map_lang in none ${keybindings_map_langs}; do
        for pp in "${A_KEYBINDINGS_MAP_PANEL_POSITIONS[@]}"; do
            for sl in "${A_KEYBINDINGS_MAP_SIDEBAR_LOCATIONS[@]}"; do
                for fc in "${A_KEYBINDINGS_MAP_FOCI[@]}"; do
                    #echo "lang=${keybindings_map_lang} pp=$pp, sl=$sl, fc=$fc"

                    if [ "${keybindings_map_lang}" != "" ] && [ "${keybindings_map_lang}" != "none" ]; then
                        keybindings-duplicate.py -F juke,split,${keybindings_map_lang} -m ${KEYBINDINGS_MAP_MODIFIERS} -w "${when_prefix} && config.workbench.sideBar.location == '${sl}' && panelPosition == '${pp}' && ${fc}" > ${map_file}.${keybindings_map_lang}.jsonc
                    else
                        keybindings-duplicate.py -F juke,split -m ${KEYBINDINGS_MAP_MODIFIERS} -w "${when_prefix} && config.workbench.sideBar.location == '${sl}' && panelPosition == '${pp}' && ${fc}" > ${map_file}.${keybindings_map_lang}.jsonc
                    fi
                done
            done
        done
    done

    keybindings_merge ${map_file}*

    local mf dmf

    for mf in ${map_file}.*; do
        if [ -f "${mf}" ]; then
            dmf="${mf//${epoch}./}"
            dmf="${dmf//.none.jsonc/.jsonc}"
            dmf="${dmf//keybindings_map/keybindings.map}"
            if [ -f "${dmf}" ]; then
                echo "dmf = ${dmf}"

                if [ ${make_mode} -eq 1 ]; then
                    mv -f "${mf}" "${dmf}"
                    # create a normalized, sorted map using corpus conversion then sort
                    local sort_args
                    sort_args="${KEYBINDINGS_SORT_ARGUMENTS:- -p when -s key -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters}"
                    keybindings-corpus.py -c "${dmf}" > "${dmf}.tmp.jsonc"
                    keybindings-sort.py ${sort_args} < "${dmf}.tmp.jsonc" > "${dmf}"
                    sed -i '/enabledMap/s//enabled/g' "${dmf}"
                    [ -f "${dmf}.tmp.jsonc" ] && rm -f "${dmf}.tmp.jsonc"
                    ls -l "${dmf}"
                else
                    ls -l "${mf}" && rm -f "${mf}"
                fi

            fi
        fi
    done

}

keybindings_map_array() {
    local encoded_words=()
    local item=""
    for item in "$@"; do
        if [[ "${item}" == *" "* ]]; then
            encoded_words+=("'${item}'")
        else
            encoded_words+=("$(printf '%q' "$item")")
        fi
    done

    printf '%s' "${encoded_words[*]}"
}

keybindings_merge() {
    [ "${1}" == "" ] && printf '\nusage: keybindings_merge <file1.json> ...\n\n' && return 1

    local left="${1}"

    [ ! -r "${left}" ] && printf "\nERROR: '${left}' file not found readable\n\n" && return 2

    # echo all=${@}

    local use_jq=0
    if type -P jq &> /dev/null; then
        use_jq=1
    fi

    local pure_json=1

    local merge_file merge_files=0
    for merge_file in ${@}; do
        let merge_files=${merge_files}+1

        #echo "# [${merge_files}] ${merge_file}"
        #ls -l ${merge_file}

        if [ ${pure_json} -eq 1 ]; then
            if [ ${use_jq} -eq 1 ]; then
                if ! cat "${merge_file}" | jq -r . &> /dev/null; then
                    pure_json=0
                fi
            else
                pure_json=0
            fi
        fi

    done

    if [ ${pure_json} -eq 1 ]; then
        if [ ${use_jq} -eq 1 ]; then
            # echo they are pure json, use jq
            # jq -s 'add' file1.json file2.json ...
            jq -s 'add ' ${@} | keybindings-sort.py | jq -r .
            return $?
        fi
    fi

    # use keybindings-merge.py

    if [ ${merge_files} -le 1 ]; then
        printf "\nERROR: to merge, at least two input files are required\n\n" && return 3
    else
        if [ ${merge_files} -eq 2 ]; then
            keybindings-merge.py "${1}" "${2}" --out keybindings_merge.jsonc &> /dev/null && cat keybindings_merge.jsonc | keybindings-sort.py && rm -f keybindings_merge.jsonc
        else
            printf "\nERROR: to merge, exactly two input files are required\n\n" && return 3
        fi
    fi
}

# main

export KEYBINDINGS_MAP_FOCI="$(keybindings_map_array "${A_KEYBINDINGS_MAP_FOCI[@]}")"
export KEYBINDINGS_MAP_PANEL_POSITIONS="$(keybindings_map_array "${A_KEYBINDINGS_MAP_PANEL_POSITIONS[@]}")"
export KEYBINDINGS_MAP_SIDEBAR_LOCATIONS="$(keybindings_map_array "${A_KEYBINDINGS_MAP_SIDEBAR_LOCATIONS[@]}")"

[ "${0}" != "${BASH_SOURCE}" ] && return # if it was sourced

# execute

keybindings_map ${@}
