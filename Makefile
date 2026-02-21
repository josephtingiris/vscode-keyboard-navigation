
.DEFAULT_GOAL := help
.PHONY: help all build clean corpus corpora extension test tests

# default: show help when `make` is run with no args
help:
	@echo "usage: make [target]"
	@echo
	@echo "Available Targets:"
	@echo "  help                    - show this message (default)"
	@echo "  all                     - make all targets"
	@echo "  build                   - build (delegates to subdirs)"
	@echo "  clean                   - clean build/test artifacts"
	@echo "  corpus                  - generate full corpus in references/"
	@echo "  corpora                 - alias for corpus"
	@echo "  extension               - make extension (delegates to ./extension/)"
	@echo "  test                    - run tests (delegates to ./tests/)"
	@echo "  tests                   - alias for test"
	@echo

#
# init
#

# directories with their own Makefiles
SUBDIRS := extension tests

#
# targets
#

all: clean corpus build test

build:
	@echo "++ Building subdirectories ..."
	@echo
	@for d in $(SUBDIRS); do \
		echo $(MAKE) -C $$d build || true; \
		echo; \
		$(MAKE) -C $$d build || true; \
		echo; \
	done
	@echo "++ Subdirectory builds complete."
	@echo

clean:
	@echo "++ Cleaning repository (delegating to sub-makes) ..."
	@echo
	@for d in $(SUBDIRS); do \
		$(MAKE) -C $$d clean || true; \
	done
	@echo "++ Repository clean complete."
	@echo

corpus:
	@echo "++ Updating reference keybindings corpus files ..."
	@keybindings-corpus.py | keybindings-sort.py > references/keybindings.corpus.jsonc
	@keybindings-corpus.py -n all | keybindings-sort.py > references/keybindings.corpus.all.jsonc
	@keybindings-corpus.py -n emacs | keybindings-sort.py > references/keybindings.corpus.emacs.jsonc
	@keybindings-corpus.py -n kbm | keybindings-sort.py > references/keybindings.corpus.kbm.jsonc
	@keybindings-corpus.py -n vi | keybindings-sort.py > references/keybindings.corpus.vi.jsonc
	@echo

corpora: corpus

extension:
	@echo "++ Making all in extension/ ..."
	@echo
	@echo $(MAKE) -C extension all
	@echo
	$(MAKE) -C extension all

test:
	@echo "++ Running tests ..."
	@echo
	@$(MAKE) -C tests tests
	@echo

tests: test