[ "${0}" == "${BASH_SOURCE}" ] && printf "\nERROR: do not execute this! (instead, use 'source ${0}')\n\n" && exit 1
[ ! -f "${BASH_SOURCE%/*}/../../.bash_profile" ] && [ $(wc -l 2> /dev/null < "${BASH_SOURCE}") -gt 2 ] && bd_ansi fg_red "Loading -> ${BASH_SOURCE} ... from ${PWD}" && echo

# repo exports
