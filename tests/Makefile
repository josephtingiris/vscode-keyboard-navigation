
.DEFAULT_GOAL := help
.PHONY: help all build clean test tests $(TARGETS)

# default: show help when `make` is run with no args
help:
	@echo "usage: make [target]"
	@echo
	@echo "Available Targets:"
	@echo "  help                    - show this message (default)"
	@echo "  all                     - make all targets"
	@echo "  build                   - run tests/ build"
	@echo "  clean                   - clean tests/ artifacts"
	@echo "  tests                   - run all tests, including scripts"
	@echo "  test                    - alias for tests"
	@echo
	@echo "Script Targets:"
	@for t in $(TARGETS); do \
		echo "  $$t"; \
	done
	@echo

#
# init
#

# find executables with a shebang
SCRIPTS := $(shell find . -type f -perm /111 -print | sort | xargs -I{} sh -c 'head -n1 "{}" 2>/dev/null | sed -n "1p" | grep -q "^#!" && echo "{}" || true' | sed 's|^./||')

# dynamic target names for scripts with a shebang (e.g. "test.example" for "test/example.sh")
TARGETS := $(foreach s,$(SCRIPTS),$(subst /,.,$(basename $(s))))

# dynamic rule generator: create a rule for each discovered script
define RUN_RULE
$(1):
	@echo "++ Running $(2) ..."
	@echo --cut--
	@./$(2)
	@echo --cut--
	@echo
endef
$(foreach s,$(SCRIPTS),$(eval $(call RUN_RULE,$(subst /,.,$(basename $(s))),$(s))))

#
# targets
#

all: build clean tests

build:
	@echo "++ Building tests/ ..."
	@echo

clean:
	@echo "++ Cleaning tests/ artifacts ..."
	@echo

	# remove __pycache__
	-@rm -rf __pycache__

	# remove any other temporary files in extension/
	-@rm -rf node_modules .cache tmp

tests: $(TARGETS)

test: tests