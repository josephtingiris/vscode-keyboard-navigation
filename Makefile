
.DEFAULT_GOAL := help
.PHONY: help all build clean test tests corpus corpora extension install map maps references uninstall

# default: show help when `make` is run with no args
help:
	@echo "usage: make [target]"
	@echo
	@echo "Available Targets:"
	@echo "  help                    - show this message (default)"
	@echo "  all                     - make all targets"
	@echo "  build                   - build (delegates to subdirs)"
	@echo "  clean                   - clean all artifacts"
	@echo "  corpora                 - generate all corpus files in references/"
	@echo "  corpus                  - alias for corpora"
	@echo "  install                 - install development packages"
	@echo "  maps                    - generate all map files in references/"
	@echo "  map                     - alias for maps"
	@echo "  extension               - make extension in extension/"
	@echo "  surfaces                - generalte all surface files in references/"
	@echo "  surface                 - alias for surfaces"
	@echo "  tests                   - run all tests in tests/"
	@echo "  test                    - alias for tests"
	@echo "  uninstall               - uninstall development packages"
	@echo

#
# init
#

# directories with their own Makefiles
SUBDIRS := extension references tests

#
# targets
#

all: clean build tests

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
	@echo "++ Cleaning repository ..."
	@echo
	@for d in $(SUBDIRS); do \
		$(MAKE) -C $$d clean || true; \
	done

	# remove temporary directories and files
	@for r in .cache .pytest_cache .venv node_modules tmp; do \
		rm -rf $$r; \
	done

	@echo
	@echo "++ Repository clean complete."

corpora:
	@echo "++ Making corpora in references/ ..."
	@echo
	$(MAKE) -C references corpora

corpus: corpora

extension:
	@echo "++ Making all in extension/ ..."
	@echo
	$(MAKE) -C extension all

install:
	@echo "++ Installing development packages ..."
	@command -v python3 >/dev/null 2>&1 || { echo "error: python3 not found in PATH"; exit 2; }
	python3 -m pip install -e .

maps:
	@echo "++ Making maps in references/ ..."
	@echo
	$(MAKE) -C references maps

map: maps

references:
	@echo "++ Making all in references/ ..."
	@echo
	$(MAKE) -C references all

surfaces:
	@echo "++ Making surfaces in references/ ..."
	@echo
	$(MAKE) -C references surfaces

surface: surfaces

tests:
	@echo "++ Running all tests/ ..."
	@echo
	@$(MAKE) -C tests tests

test: tests

uninstall:
	@echo "++ Uninstalling development packages ..."
	@command -v python3 >/dev/null 2>&1 || { echo "error: python3 not found in PATH"; exit 2; }
	python3 -m pip uninstall -y vscode-keynav || true