
DEFAULT_GOAL := help

# find executable files with a shebang
SCRIPTS := $(shell find . -type f -perm /111 -print | xargs -I{} sh -c 'head -n1 "{}" 2>/dev/null | sed -n "1p" | grep -q "^#!" && echo "{}" || true' | sed 's|^./||')

# derive target names from script paths
TARGETS := $(foreach s,$(SCRIPTS),$(subst /,.,$(basename $(s))))

.PHONY: help tests $(TARGETS)

help:
	@echo "Tests Makefile - available targets:"
	@echo "  help   - show this message (default)"
	@echo "  tests  - run all discovered executable scripts with a shebang"
	@printf "  %-6s %s\n" "targets:" "$(TARGETS)"

# run all discovered tests
tests: $(TARGETS)

# dynamic rule generator: create a rule for each discovered script
define RUN_RULE
$(1):
	@echo "Running $(2) ..."
	@./$(2)
endef

$(foreach s,$(SCRIPTS),$(eval $(call RUN_RULE,$(subst /,.,$(basename $(s))),$(s))))

