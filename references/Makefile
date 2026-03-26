
.DEFAULT_GOAL := help
.PHONY: help all build clean test tests corpus corpora map maps maps-quick surfaces surface

# default: show help when `make` is run with no args
help:
	@echo "usage: make [target]"
	@echo
	@echo "Available Targets:"
	@echo "  help                    - show this message (default)"
	@echo "  all                     - make all targets"
	@echo "  build                   - run references/ build"
	@echo "  clean                   - clean references/ artifacts"
	@echo "  corpora                 - generate all corpus files"
	@echo "  corpus                  - alias for corpora"
	@echo "  maps                    - generate all map files"
	@echo "  map                     - alias for maps"
	@echo "  maps-quick              - quick/smoke map generation (fast validation)"
	@echo "  surfaces                - generate all surface files"
	@echo "  surface                 - alias for surfaces"
	@echo "  tests                   - run all tests in ../tests/"
	@echo "  test                    - alias for tests"
	@echo

#
# init
#

LETTER_KEY_GROUPS ?= emacs kbm vi
#LETTER_KEY_GROUPS := vi

# map defaults; can be overridden via environment variables.
# NOTE: env overrides may be shell-escaped word lists (for example values
# exported from Bash arrays in etc/bash.d/keybindings-map.sh).
KEYBINDINGS_MAP_FOCI ?= auxiliaryBarFocus editorFocus 'editorFocus && editorTextFocus' 'editorFocus && panelFocus' panelFocus 'panelFocus && sideBarFocus' 'panelFocus && terminalFocus' statusBarFocused terminalFocus
KEYBINDINGS_MAP_MODIFIERS ?= alt,shift+alt,ctrl+alt,ctrl+alt+meta,ctrl+shift+alt
KEYBINDINGS_MAP_PANEL_POSITIONS ?= top bottom left right
KEYBINDINGS_MAP_SIDEBAR_LOCATIONS ?= left right

KEYBINDINGS_SORT_ARGUMENTS ?= -w focal-invariant

#
# targets
#

all: clean build tests

build: corpora maps
	@echo "++ Building references/ ..."
	@echo

clean:
	@echo "++ Cleaning references/ artifacts ..."
	@echo

	# remove any other temporary files in references/
	-@rm -rf node_modules .cache tmp

corpora:
	@echo "++ Updating references keybindings corpus files ..."
	@echo

	# none
	@keybindings-corpus.py | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.corpus.jsonc

	# letter-key groups
	@for lkg in $(LETTER_KEY_GROUPS); do \
		../bin/keybindings-corpus.py -n $$lkg | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.corpus.$$lkg.jsonc; \
	done

	# all
	@keybindings-corpus.py -n all | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.corpus.all.jsonc
	@echo

corpus: corpora

maps:
	@echo "++ Updating references keybindings map files ..."
	@echo

	# none & letter-key groups
	@for lkg in none $(LETTER_KEY_GROUPS); do \
		../bin/keybindings-map.sh --make $$lkg; \
	done

	# all
	@echo; \
	echo '[]' > keybindings.map.all.jsonc; \
	for mf in keybindings.map.*jsonc; do \
		MAP_FILE="$$mf"; \
		ls -lh $${MAP_FILE}; \
		[[ "$${MAP_FILE}" == *"all.jsonc" ]] && continue; \
		../bin/keybindings-merge.py $${MAP_FILE} keybindings.map.all.jsonc --out keybindings.map.all.tmp.jsonc 1> /dev/null; \
		../bin/keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) < keybindings.map.all.tmp.jsonc > keybindings.map.all.jsonc; \
		[ -f keybindings.map.all.tmp.jsonc ] && rm -f  keybindings.map.all.tmp.jsonc ]; \
	done
	@echo

map: maps

maps-quick:
	@echo "++ Running quick map generation (none + vi) ..."
	@echo
	# generate only a small representative subset to validate changes quickly
	@../bin/keybindings-map.sh --make none
	# there should not be any diffs
	@git diff keybindings.map.jsonc
	@echo

surfaces:
	@echo "++ Updating references keybindings surface files ..."
	@echo

	# none
	@../bin/keybindings-merge.py keybindings.corpus.jsonc keybindings.map.jsonc --prefer left --out keybindings.merged.surface.jsonc 1> /dev/null
	@cat keybindings.merged.surface.jsonc | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.surface.jsonc
	@cat keybindings.surface.jsonc | keybindings-duplicate.py --detect --correct-duplicate-ids > keybindings.merged.surface.jsonc
	@cat keybindings.merged.surface.jsonc | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.surface.jsonc
	@rm -f keybindings.merged.surface.jsonc

	# letter-key groups
	@for lkg in $(LETTER_KEY_GROUPS); do \
		../bin/keybindings-merge.py keybindings.corpus.$$lkg.jsonc keybindings.map.$$lkg.jsonc --prefer left --out keybindings.merged.surface.$$lkg.jsonc 1> /dev/null; \
		cat keybindings.merged.surface.$$lkg.jsonc | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.surface.$$lkg.jsonc; \
		cat keybindings.surface.$$lkg.jsonc | keybindings-duplicate.py --detect --correct-duplicate-ids > keybindings.merged.surface.$$lkg.jsonc; \
		cat keybindings.merged.surface.$$lkg.jsonc | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.surface.$$lkg.jsonc; \
		rm -f keybindings.merged.surface.$$lkg.jsonc; \
	done

	# all
	@../bin/keybindings-merge.py keybindings.corpus.all.jsonc keybindings.map.all.jsonc --prefer left --out keybindings.merged.surface.all.jsonc 1> /dev/null
	@cat keybindings.merged.surface.all.jsonc | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.surface.all.jsonc
	@cat keybindings.surface.all.jsonc | keybindings-duplicate.py --detect --correct-duplicate-ids > keybindings.merged.surface.all.jsonc
	@cat keybindings.merged.surface.all.jsonc | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.surface.all.jsonc
	@rm -f keybindings.merged.surface.all.jsonc
	@echo

surface: surfaces

tests:
	@echo "++ Running tests ..."
	@echo
	@$(MAKE) -C ../tests tests

test: tests