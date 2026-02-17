
.DEFAULT_GOAL := help
.PHONY: help all build test tests clean extension

# subdirectories with their own Makefiles
SUBDIRS := extension

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

extension:
	@echAo "Delegating to extension/Makefile (default target) ..."
	@$(MAKE) -C extension


# run tests across repository (delegate to tests/Makefile)
test:
	@echo "Running tests across repository..."
	@$(MAKE) -C tests tests

# alias `make tests` to `make test`
tests: test

clean:
	@echo "Cleaning repository (delegating to sub-makes) ..."
	@for d in $(SUBDIRS); do \
		$(MAKE) -C $$d clean || true; \
	done
	@echo "Repository clean complete."
