
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
FOCUS_COMPONENTS := auxiliaryBarFocus editorFocus editorTextFocus 'panelFocus && !editorFocs' sideBarFocus terminalFocus
SIDEBAR_LOCATIONS := left right
PANEL_LOCATIONS := top bottom left right

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
	@keybindings-corpus.py | keybindings-sort.py > keybindings.corpus.jsonc
	@keybindings-corpus.py -n all | keybindings-sort.py > keybindings.corpus.all.jsonc
	@keybindings-corpus.py -n emacs | keybindings-sort.py > keybindings.corpus.emacs.jsonc
	@keybindings-corpus.py -n kbm | keybindings-sort.py > keybindings.corpus.kbm.jsonc
	@keybindings-corpus.py -n vi | keybindings-sort.py > keybindings.corpus.vi.jsonc
	@echo

corpus: corpora

maps:
#echo "-w \"config.keyboardNavigation.enabled && config.keyboardNavigation.keys.letters == 'vi' && config.workbench.sideBar.location == 'right' && $$f\""
	@for s in $(SIDEBAR_LOCATIONS); do \
		echo; \
		for f in $(FOCUS_COMPONENTS); do \
			echo "keybindings-duplicate.py -F juke,split,vi -m alt,shift+alt,ctrl+alt,ctrl+alt+meta,ctrl+shift+alt -w \"config.keyboardNavigation.enabled && config.keyboardNavigation.keys.letters == 'vi' && config.workbench.sideBar.location == '$$s' && $$f\"" || true; \
			echo; \
		done; \
	done
	#@keybindings-duplicate.py -F juke,split,vi -m alt,shift+alt,ctrl+alt,ctrl+alt+meta,ctrl+shift+alt | keybindings-sort.py

	@echo

map: maps

tests:
	@echo "++ Running tests ..."
	@echo
	@$(MAKE) -C ../tests tests

test: tests