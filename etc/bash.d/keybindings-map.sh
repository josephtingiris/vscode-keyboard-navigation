#
# (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
#
# related to generating keybindings 'maps'
#

# globals (exports)

# authoritative defaults; these are exported as shell-escaped scalar strings (below)
A_KEYBINDINGS_MAP_FOCI=(auxiliaryBarFocus editorFocus 'editorFocus && editorTextFocus' 'editorFocus && panelFocus' panelFocus 'panelFocus && sideBarFocus' 'panelFocus && terminalFocus' statusBarFocused terminalFocus)
# auxiliaryBarFocus editorFocus editorTextFocus filesExplorerFocus inDebugRepl inQuickOpen listFocus listHasSelectionOrFocus notificationFocus panelFocus sideBarFocus terminalFocus
# auxiliaryBarFocus editorFocus editorTextFocus panelFocus sideBarFocus terminalFocus
A_KEYBINDINGS_MAP_MODIFIERS=(alt,shift+alt,ctrl+alt,ctrl+alt+meta,ctrl+shift+alt)
A_KEYBINDINGS_MAP_PANEL_POSITIONS=(top bottom left right)
A_KEYBINDINGS_MAP_SIDEBAR_LOCATIONS=(left right)

# primarily for references/Makefile
export KEYBINDINGS_MAP_FOCI="$(_keynav_array_to_string "${A_KEYBINDINGS_MAP_FOCI[@]}")"
export KEYBINDINGS_MAP_MODIFIERS="$(_keynav_array_to_string "${A_KEYBINDINGS_MAP_MODIFIERS[@]}")"
export KEYBINDINGS_MAP_PANEL_POSITIONS="$(_keynav_array_to_string "${A_KEYBINDINGS_MAP_PANEL_POSITIONS[@]}")"
export KEYBINDINGS_MAP_SIDEBAR_LOCATIONS="$(_keynav_array_to_string "${A_KEYBINDINGS_MAP_SIDEBAR_LOCATIONS[@]}")"

# functions

keybindings_map() {

    for pp in "${A_KEYBINDINGS_MAP_PANEL_POSITIONS[@]}"; do
        for sl in "${A_KEYBINDINGS_MAP_SIDEBAR_LOCATIONS[@]}"; do
            for fc in "${A_KEYBINDINGS_MAP_FOCI[@]}"; do
                echo "pp=$pp, sl=$sl, fc=$fc"
            done
        done
    done
}

# main
