
.DEFAULT_GOAL := help
.PHONY: help all build clean test tests corpus corpora extension map maps references

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
	@echo "  maps                    - generate all map files in references/"
	@echo "  map                     - alias for maps"
	@echo "  extension               - make extension in extension/"
	@echo "  tests                   - run all tests in tests/"
	@echo "  test                    - alias for tests"
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

	# remove .pytest_cache
	-@rm -rf .pytest_cache

	# remove any other temporary files
	-@rm -rf node_modules .cache tmp

	@echo
	@echo "++ Repository clean complete."

corpus:
	@echo "++ Making corpus in references/ ..."
	@echo
	$(MAKE) -C references corpus

corpora: corpus

extension:
	@echo "++ Making all in extension/ ..."
	@echo
	$(MAKE) -C extension all

maps:
	@echo "++ Making maps in references/ ..."
	@echo
	$(MAKE) -C references maps

map: maps

references:
	@echo "++ Making all in references/ ..."
	@echo
	$(MAKE) -C references all

tests:
	@echo "++ Running all tests/ ..."
	@echo
	@$(MAKE) -C tests tests

test: tests