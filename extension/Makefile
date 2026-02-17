
.DEFAULT_GOAL := help
.PHONY: help all build test tests clean

# default: show help
help:
	@echo "Extension Makefile - available targets:"
	@echo "  help   - show this message (default)"
	@echo "  all    - clean, build, test (delegates)"
	@echo "  build  - run extension build steps (none by default)"
	@echo "  test   - run extension tests"
	@echo "  clean  - clean extension artifacts"

all: clean build test

build:
	@echo "Extension: no build steps defined"

test:
	@echo "Running extension tests ..."
	# delegate to repository-level tests/ Makefile
	@$(MAKE) -C ../tests tests

# alias `make tests` to `make test`
tests: test

clean:
	@echo "Cleaning extension artifacts ..."
	# remove test-created mock vscode module placed under project node_modules
	-@rm -rf ../node_modules/vscode
	# remove any other temporary files
	-@rm -rf node_modules .cache tmp
