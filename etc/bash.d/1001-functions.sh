#
# (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
#
# reusable functions
#

_keynav_array_to_string() {
    local encoded_words=()
    local item=""
    for item in "$@"; do
        encoded_words+=("$(printf '%q' "$item")")
    done

    printf '%s' "${encoded_words[*]}"
}
