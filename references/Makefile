
.DEFAULT_GOAL := help
.PHONY: help all build clean test tests corpus corpora map maps surfaces surface

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
	@echo "  surfaces                - generate all surface files"
	@echo "  surface                 - alias for surfaces"
	@echo "  tests                   - run all tests in ../tests/"
	@echo "  test                    - alias for tests"
	@echo

#
# init
#

# auxiliaryBarFocus editorFocus editorTextFocus filesExplorerFocus inDebugRepl inQuickOpen listFocus listHasSelectionOrFocus notificationFocus panelFocus sideBarFocus terminalFocus
# auxiliaryBarFocus editorFocus editorTextFocus panelFocus sideBarFocus terminalFocus
FOCUS_COMPONENTS := auxiliaryBarFocus editorFocus 'editorFocus && editorTextFocus' 'editorFocus && panelFocus' panelFocus 'panelFocus && sideBarFocus' 'panelFocus && terminalFocus' sideBarFocus
LETTER_NAV_GROUPS := emacs kbm vi
#LETTER_NAV_GROUPS := vi
MAP_MODIFIERS := alt,shift+alt,ctrl+alt,ctrl+alt+meta,ctrl+shift+alt
PANEL_POSITIONS := top bottom left right
SIDEBAR_LOCATIONS := left right
KEYBINDINGS_SORT_ARGUMENTS := -p when -s key -g positive -w focal-invariant --when-prefix config.keyboardNavigation.enabled,config.keyboardNavigation.keys.letters

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
	@for lng in $(LETTER_NAV_GROUPS); do \
		../bin/keybindings-corpus.py -n $$lng | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.corpus.$$lng.jsonc; \
	done

	# all
	@keybindings-corpus.py -n all | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.corpus.all.jsonc
	@echo

corpus: corpora

maps:
	@echo "++ Updating references keybindings map files ..."
	@echo

	# none & letter-key groups
	@for lng in none $(LETTER_NAV_GROUPS); do \
		WHEN_PREFIX="config.keyboardNavigation.enabledMap"; \
		if [ "$$lng" != "" ] && [ "$$lng" != "none" ]; then \
			WHEN_PREFIX+=" && config.keyboardNavigation.keys.letters == '$$lng'"; \
			MAP_FILE="keybindings.map.$$lng.jsonc"; \
		else \
			# none; \
			MAP_FILE="keybindings.map.jsonc"; \
		fi; \
		echo "# + $${MAP_FILE}"; \
		echo "# + WHEN_PREFIX="$${WHEN_PREFIX}; \
 \
		echo '[]' > $${MAP_FILE}; \
		if [ "$$lng" != "" ] && [ "$$lng" != "none" ]; then \
			echo "# + $$lng panel & sidebar locations"; \
		else \
			# none; \
			echo "# + juke & split panel & sidebar locations"; \
		fi; \
 \
		for pp in $(PANEL_POSITIONS); do \
			for sl in $(SIDEBAR_LOCATIONS); do \
				for fc in $(FOCUS_COMPONENTS); do \
					#echo "# + $$lng $$sl $$fc"; \
					if [ "$$lng" != "" ] && [ "$$lng" != "none" ]; then \
						../bin/keybindings-duplicate.py -F juke,split,$$lng -m $(MAP_MODIFIERS) -w "$${WHEN_PREFIX} && config.workbench.sideBar.location == '$$sl' && panelPosition == '$$pp' && $$fc" > $${MAP_FILE}.psf.jsonc; \
					else \
						# none; \
						../bin/keybindings-duplicate.py -F juke,split -m $(MAP_MODIFIERS) -w "$${WHEN_PREFIX} && config.workbench.sideBar.location == '$$sl' && panelPosition == '$$pp' && $$fc" > $${MAP_FILE}.psf.jsonc; \
					fi; \
					../bin/keybindings-merge.py $${MAP_FILE}.psf.jsonc $${MAP_FILE} --out $${MAP_FILE}.merged.jsonc 1> /dev/null; \
					mv -f $${MAP_FILE}.merged.jsonc $${MAP_FILE}; \
				done; \
			[ -f $${MAP_FILE}.psf.jsonc ] && rm -f $${MAP_FILE}.psf.jsonc; \
			done; \
		done; \
		../bin/keybindings-corpus.py -c $${MAP_FILE} > $${MAP_FILE}.tmp.jsonc; \
		../bin/keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) < $${MAP_FILE}.tmp.jsonc > $${MAP_FILE}; \
		sed -i '/enabledMap/s//enabled/g' $${MAP_FILE}; \
		[ -f $${MAP_FILE}.tmp.jsonc ] && rm -f $${MAP_FILE}.tmp.jsonc; \
	done

	# all
	@echo; \
	echo '[]' > keybindings.map.all.jsonc; \
	for mf in keybindings.map.*jsonc; do \
		MAP_FILE="$$mf"; \
		ls -l $${MAP_FILE}; \
		[[ "$${MAP_FILE}" == *"all.jsonc" ]] && continue; \
		../bin/keybindings-merge.py $${MAP_FILE} keybindings.map.all.jsonc --out keybindings.map.all.tmp.jsonc 1> /dev/null; \
		../bin/keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) < keybindings.map.all.tmp.jsonc > keybindings.map.all.jsonc; \
		[ -f keybindings.map.all.tmp.jsonc ] && rm -f  keybindings.map.all.tmp.jsonc ]; \
	done
	@echo

map: maps

surfaces:
	@echo "++ Updating references keybindings surface files ..."
	@echo

	# none
	@../bin/keybindings-merge.py keybindings.corpus.jsonc keybindings.map.jsonc --prefer left --out keybindings.merged.surface.jsonc 1> /dev/null
	@cat keybindings.merged.surface.jsonc | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.surface.jsonc
	@rm -f keybindings.merged.surface.jsonc

	# letter-key groups
	@for lng in $(LETTER_NAV_GROUPS); do \
		../bin/keybindings-merge.py keybindings.corpus.$$lng.jsonc keybindings.map.$$lng.jsonc --prefer left --out keybindings.merged.surface.$$lng.jsonc 1> /dev/null; \
		cat keybindings.merged.surface.$$lng.jsonc | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.surface.$$lng.jsonc; \
		rm -f keybindings.merged.surface.$$lng.jsonc; \
	done

	# all
	@../bin/keybindings-merge.py keybindings.corpus.all.jsonc keybindings.map.all.jsonc --prefer left --out keybindings.merged.surface.all.jsonc 1> /dev/null
	@cat keybindings.merged.surface.all.jsonc | keybindings-sort.py $(KEYBINDINGS_SORT_ARGUMENTS) > keybindings.surface.all.jsonc
	@rm -f keybindings.merged.surface.all.jsonc
	@echo

surface: surfaces

tests:
	@echo "++ Running tests ..."
	@echo
	@$(MAKE) -C ../tests tests

test: tests