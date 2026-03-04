#!/usr/bin/env bash
#
# (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
#
# generate keybindings 'maps'
#

# globals (exports)

# authoritative defaults; these are exported if sourced

export A_KEYBINDINGS_MAP_FOCI=(auxiliaryBarFocus editorFocus 'editorFocus && editorTextFocus' 'editorFocus && panelFocus' panelFocus 'panelFocus && sideBarFocus' 'panelFocus && terminalFocus' statusBarFocused terminalFocus)
if [ "${KEYBINDINGS_MAP_FOCUS}" != "" ]; then
    export A_KEYBINDINGS_MAP_FOCI=("${KEYBINDINGS_MAP_FOCUS//\\/}")
fi

if [ "${0}" != "${BASH_SOURCE}" ] || [ "${KEYBINDINGS_MAP_MODIFIERS}" == "" ]; then
    export KEYBINDINGS_MAP_MODIFIERS="alt,shift+alt,ctrl+alt,ctrl+alt+meta,ctrl+shift+alt"
fi
export KEYBINDINGS_MAP_MODIFIERS="${KEYBINDINGS_MAP_MODIFIERS}"

if [ "${0}" != "${BASH_SOURCE}" ] || [ "${KEYBINDINGS_SORT_ARGUMENTS}" == "" ]; then
    export KEYBINDINGS_SORT_ARGUMENTS="-p when -s key -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters --when-regex config.keyboardNavigation.chords"
fi
export KEYBINDINGS_SORT_ARGUMENTS="${KEYBINDINGS_SORT_ARGUMENTS}"

# immutable
A_KEYBINDINGS_MAP_PANEL_POSITIONS=(top bottom left right)
A_KEYBINDINGS_MAP_SIDEBAR_LOCATIONS=(left right)

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

    [ "${1}" == "" ] && printf "\nusage: keybindings_map [--make] <letter-key group name(s)|none>\n\n" && return 1

    local keybindings_map_letter_key_group keybindings_map_letter_key_groups="${1//,/ }"

    local epoch="$(date +%s)"

    local map_file="keybindings_map.${epoch}"

    local when_prefix

    local pp fl fc m1 m2

    for keybindings_map_letter_key_group in ${keybindings_map_letter_key_groups}; do
        if [ ${make_mode} -eq 1 ]; then
            echo "make map letter_key_group=${keybindings_map_letter_key_group}"
        fi

        if [ "${WHEN_PREFIX}" == "" ]; then
            when_prefix="config.keyboardNavigation.enabledMap"
            if [ "${keybindings_map_letter_key_group}" != "" ] && [ "${keybindings_map_letter_key_group}" != "none" ]; then
                when_prefix+=" && config.keyboardNavigation.keys.letters == '${keybindings_map_letter_key_group}'"
            fi
        else
            when_prefix="${WHEN_PREFIX}"
        fi

        if [ ${make_mode} -eq 0 ]; then
            echo "// ${when_prefix}"
        fi

        for pp in "${A_KEYBINDINGS_MAP_PANEL_POSITIONS[@]}"; do
            #echo "make map letter_key_group=${keybindings_map_letter_key_group} pp=$pp"

            for sl in "${A_KEYBINDINGS_MAP_SIDEBAR_LOCATIONS[@]}"; do
                #echo "make map letter_key_group=${keybindings_map_letter_key_group} pp=$pp, sl=$sl"

                for fc in "${A_KEYBINDINGS_MAP_FOCI[@]}"; do
                    #echo "make map letter_key_group=${keybindings_map_letter_key_group} pp=$pp, sl=$sl, fc=$fc"

                    touch ${map_file}.${keybindings_map_letter_key_group}.jsonc

                    if [ "${keybindings_map_letter_key_group}" != "" ] && [ "${keybindings_map_letter_key_group}" != "none" ]; then
                        keybindings-duplicate.py -F juke,split,${keybindings_map_letter_key_group} -m ${KEYBINDINGS_MAP_MODIFIERS} -w "${when_prefix} && config.workbench.sideBar.location == '${sl}' && panelPosition == '${pp}' && ${fc}" > ${map_file}.${keybindings_map_letter_key_group}.m1.jsonc
                    else
                        keybindings-duplicate.py -F juke,split -m ${KEYBINDINGS_MAP_MODIFIERS} -w "${when_prefix} && config.workbench.sideBar.location == '${sl}' && panelPosition == '${pp}' && ${fc}" > ${map_file}.${keybindings_map_letter_key_group}.m1.jsonc
                    fi

                    keybindings_merge ${map_file}.${keybindings_map_letter_key_group}.jsonc ${map_file}.${keybindings_map_letter_key_group}.m1.jsonc > ${map_file}.${keybindings_map_letter_key_group}.m2.jsonc

                    mv -f ${map_file}.${keybindings_map_letter_key_group}.m2.jsonc ${map_file}.${keybindings_map_letter_key_group}.m1.jsonc
                    mv -f ${map_file}.${keybindings_map_letter_key_group}.m1.jsonc ${map_file}.${keybindings_map_letter_key_group}.jsonc
                done

            done
        done
    done

    local mf mfs dmf

    let mfs=0
    for mf in ${map_file}.*; do
        if [ -f "${mf}" ]; then
            let mfs=${mfs}+1

            # add corpus comments
            keybindings-corpus.py -c "${mf}" > "${mf}.coco" && mv -f "${mf}.coco" "${mf}"
            sed -e '/enabledMap/s//enabled/g' "${mf}" -i

            if [ ${make_mode} -eq 1 ]; then
                dmf="${mf//${epoch}./}"
                dmf="${dmf//.none.jsonc/.jsonc}"
                dmf="${dmf//keybindings_map/keybindings.map}"
                if [ -f "${dmf}" ]; then
                    echo "make dmf = ${dmf}"

                    keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} < "${mf}" > "${dmf}"
                else
                    if [ -f "references/${dmf}" ]; then
                        echo "make dmf = references/${dmf}"

                        keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} < "${mf}" > references/"${dmf}"
                    fi
                fi

                rm -f "${mf}" 2> /dev/null
                continue
            fi

            #echo keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS}
            keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} < "${mf}"
            rm -f "${mf}" 2> /dev/null
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
            jq -s 'add ' ${@} | keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} | jq -r .
            return $?
        fi
    fi

    # use keybindings-merge.py

    if [ ${merge_files} -le 1 ]; then
        printf "\nERROR: to merge, at least two input files are required\n\n" && return 3
    else
        if [ ${merge_files} -eq 2 ]; then
            keybindings-merge.py "${1}" "${2}" --out keybindings_merge.jsonc &> /dev/null && cat keybindings_merge.jsonc | keybindings-sort.py ${KEYBINDINGS_SORT_ARGUMENTS} && rm -f keybindings_merge.jsonc
        else
            printf "\nERROR: to merge, exactly two input files are required\n\n" && return 3
        fi
    fi
}

usage() {
    printf "\nusage: $(basename "$0") [--make] <letter-key group name(s)|none>\n\n"

    echo "options:"
    echo
    echo " - KEYBINDINGS_MAP_FOCUS"
    echo " - KEYBINDINGS_MAP_MODIFIERS"
    echo " - KEYBINDINGS_SORT_ARGUMENTS"
    echo

    echo "examples:"
    echo
    echo "KEYBINDINGS_MAP_FOCUS=\"inQuickEdit && editorFocus\" $(basename $0) vi"
    echo "KEYBINDINGS_MAP_MODIFIERS=shift+alt KEYBINDINGS_MAP_FOCUS=\"inQuickEdit\" $(basename $0) vi"
    echo "WHEN_PREFIX=\"config.keyboardNavigation.enabled && config.keyboardNavigation.keys.letters == 'vi'\" KEYBINDINGS_MAP_MODIFIERS=alt,shift+alt KEYBINDINGS_MAP_FOCUS=\"inQuickEdit\" $(basename $0) vi"
    echo

    exit 99
}

# main

export KEYBINDINGS_MAP_FOCI="$(keybindings_map_array "${A_KEYBINDINGS_MAP_FOCI[@]}")"
export KEYBINDINGS_MAP_PANEL_POSITIONS="$(keybindings_map_array "${A_KEYBINDINGS_MAP_PANEL_POSITIONS[@]}")"
export KEYBINDINGS_MAP_SIDEBAR_LOCATIONS="$(keybindings_map_array "${A_KEYBINDINGS_MAP_SIDEBAR_LOCATIONS[@]}")"

[ "${0}" != "${BASH_SOURCE}" ] && return # if it was sourced

# execute

[ "${1}" == "" ] && usage

keybindings_map ${@}
