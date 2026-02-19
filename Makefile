
.DEFAULT_GOAL := help
.PHONY: help all build test tests clean extension

# subdirectories with their own Makefiles
SUBDIRS := extension tests

# show help when `make` is run with no args
help:
	@echo "Usage: make [target]"
	@echo "Targets:"
	@echo "  help    - show this message (default)"
	@echo "  all     - run clean, build, test across repository (delegates to subdirs)"
	@echo "  build   - build subprojects (delegates to subdirs)"
	@echo "  test    - run tests (delegates to tests/Makefile)"
	@echo "  clean   - clean build/test artifacts in subdirs"
	@echo "  extension - delegate to extension/Makefile default target"

all: clean build test

build:
	@echo "Building repository (delegating to sub-makes) ..."
	@for d in $(SUBDIRS); do \
		$(MAKE) -C $$d build || true; \
	done
	@echo "Repository build complete."

corpus:
	@echo "Updating reference keybindings corpus files ..."
	@keybindings-corpus.py | keybindings-sort.py > references/keybindings-corpus.jsonc
	@keybindings-corpus.py -n all | keybindings-sort.py > references/keybindings-corpus-all.jsonc
	@keybindings-corpus.py -n emacs | keybindings-sort.py > references/keybindings-corpus-emacs.jsonc
	@keybindings-corpus.py -n kbm | keybindings-sort.py > references/keybindings-corpus-kbm.jsonc
	@keybindings-corpus.py -n vi | keybindings-sort.py > references/keybindings-corpus-vi.jsonc

corpora: corpus

extension:
	@echo "Delegating to extension/Makefile (default target) ..."
	@$(MAKE) -C extension

test:
	@echo "Running tests ..."
	@$(MAKE) -C tests tests

tests: test

clean:
	@echo "Cleaning repository (delegating to sub-makes) ..."
	@for d in $(SUBDIRS); do \
		$(MAKE) -C $$d clean || true; \
	done
	@echo "Repository clean complete."
