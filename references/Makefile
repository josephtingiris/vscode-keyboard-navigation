
.DEFAULT_GOAL := help
.PHONY: help all build clean test tests corpus corpora map maps

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
	@echo "  tests                   - run all tests in ../tests/"
	@echo "  test                    - alias for tests"
	@echo

#
# init
#

# auxiliaryBarFocus editorFocus editorTextFocus filesExplorerFocus inDebugRepl inQuickOpen listFocus listHasSelectionOrFocus notificationFocus panelFocus sideBarFocus terminalFocus
# auxiliaryBarFocus editorFocus editorTextFocus panelFocus sideBarFocus terminalFocus
FOCUS_COMPONENTS := auxiliaryBarFocus editorFocus editorTextFocus 'panelFocus && !editorFocus' sideBarFocus terminalFocus
LETTER_NAV_GROUPS := emacs kbm vi
MAP_MODIFIERS := alt,shift+alt,ctrl+alt,ctrl+alt+meta,ctrl+shift+alt
PANEL_POSITIONS := top bottom left right
SIDEBAR_LOCATIONS := left right

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
	@keybindings-corpus.py | keybindings-sort.py > keybindings.corpus.jsonc

	# letter-key groups
	@for lng in $(LETTER_NAV_GROUPS); do \
		../bin/keybindings-corpus.py -n $$lng | keybindings-sort.py > keybindings.corpus.$$lng.jsonc; \
	done

	# all
	@keybindings-corpus.py -n all | keybindings-sort.py > keybindings.corpus.all.jsonc
	@echo

corpus: corpora

maps:
	@echo "++ Updating references keybindings map files ..."
	@echo

	# none
	@WHEN_PREFIX="config.keyboardNavigation.enabledMap"; \
	echo "# + keybindings.map.jsonc"; \
	../bin/keybindings-duplicate.py -F juke,split -m $(MAP_MODIFIERS) -w "$${WHEN_PREFIX}" | keybindings-sort.py > keybindings.map.tmp.jsonc; \
	../bin/keybindings-corpus.py -c keybindings.map.tmp.jsonc > keybindings.map.jsonc; \
	../bin/keybindings-sort.py < keybindings.map.jsonc > keybindings.map.tmp.jsonc; \
	mv -f keybindings.map.tmp.jsonc keybindings.map.jsonc; \
	sed -i '/enabledMap/s//enabled/g' keybindings.map.jsonc; \

	# letter-key groups
	@for lng in $(LETTER_NAV_GROUPS); do \
		WHEN_PREFIX="config.keyboardNavigation.enabledMap && config.keyboardNavigation.keys.letters == '$$lng'"; \
		#echo "WHEN_PREFIX="$${WHEN_PREFIX}; \
		MAP_FILE="keybindings.map.$$lng.jsonc"; \
		echo '[]' > $${MAP_FILE}; \
		echo "# + $${MAP_FILE}"; \
		echo "# + $$lng panel locations"; \
		for pp in $(PANEL_POSITIONS); do \
			for fc in $(FOCUS_COMPONENTS); do \
				#echo "# + $$lng $$pp $$fc"; \
				../bin/keybindings-duplicate.py -F juke,split,$$lng -m $(MAP_MODIFIERS) -w "$${WHEN_PREFIX} && panelPosition == '$$pp' && $$fc" > $${MAP_FILE}.panel.jsonc; \
				../bin/keybindings-merge.py $${MAP_FILE}.panel.jsonc $${MAP_FILE} --out $${MAP_FILE}.merged.jsonc 1> /dev/null; \
				mv -f $${MAP_FILE}.merged.jsonc $${MAP_FILE}; \
			done; \
			[ -f $${MAP_FILE}.panel.jsonc ] && rm -f $${MAP_FILE}.panel.jsonc; \
		done; \
		echo "# + $$lng sidebar locations"; \
		for sl in $(SIDEBAR_LOCATIONS); do \
			for fc in $(FOCUS_COMPONENTS); do \
				#echo "# + $$lng $$sl $$fc"; \
				../bin/keybindings-duplicate.py -F juke,split,$$lng -m $(MAP_MODIFIERS) -w "$${WHEN_PREFIX} && config.workbench.sideBar.location == '$$sl' && $$fc" > $${MAP_FILE}.sidebar.jsonc; \
				../bin/keybindings-merge.py $${MAP_FILE}.sidebar.jsonc $${MAP_FILE} --out $${MAP_FILE}.merged.jsonc 1> /dev/null; \
				mv -f $${MAP_FILE}.merged.jsonc $${MAP_FILE}; \
			done; \
			[ -f $${MAP_FILE}.sidebar.jsonc ] && rm -f $${MAP_FILE}.sidebar.jsonc; \
		done; \
		../bin/keybindings-corpus.py -c $${MAP_FILE} > $${MAP_FILE}.tmp.jsonc; \
		../bin/keybindings-sort.py < $${MAP_FILE}.tmp.jsonc > $${MAP_FILE}; \
		[ -f $${MAP_FILE}.tmp.jsonc ] && rm -f $${MAP_FILE}.tmp.jsonc; \
	done

	# all
	@echo; \
	for mf in keybindings.map.*jsonc; do \
		MAP_FILE="$$mf"; \
		ls -l $${MAP_FILE}; \
	done
	@echo

map: maps

tests:
	@echo "++ Running tests ..."
	@echo
	@$(MAKE) -C ../tests tests

test: tests