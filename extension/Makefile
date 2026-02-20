
.DEFAULT_GOAL := help
.PHONY: help all build test tests clean package package-install package-uninstall

# default: show help when `make` is run with no args
help:
	@echo "usage: make [target]"
	@echo
	@echo "Available Targets:"
	@echo "  help                    - show this message (default)"
	@echo "  all                     - make all targets"
	@echo "  build                   - run extension/ build"
	@echo "  test                    - run tests (delegates to ../tests/)"
	@echo "  tests                   - alias for test"
	@echo "  package                 - package extension into .vsix (dist/)"
	@echo "  package-install         - install the generated .vsix into VS Code"
	@echo "  package-uninstall       - uninstall the extension from VS Code"
	@echo

#
# init
#

#
# targets
#

all: clean build test package

build:
	@echo "++ Building extension/ ..."
	@echo

clean:
	@echo "++ Cleaning extension artifacts ..."
	@echo
	# remove test-created mock vscode module placed under project node_modules
	-@rm -rf ../node_modules/vscode
	# remove any other temporary files
	-@rm -rf node_modules .cache tmp

# package: create a .vsix
package:
	@echo "++ Packaging extension artifacts ..."
	@echo
	vsce package --allow-missing-repository --out dist/

# package-install: install the .vsix into VS Code
package-install:
	@echo "++ Installing package ..."
	@echo
	@NAME=$(shell node -e "console.log(require('./package.json').name)"); \
	VER=$(shell node -e "console.log(require('./package.json').version)"); \
	FILE=dist/$${NAME}-$${VER}.vsix; \
	if [ ! -f "$${FILE}" ]; then echo "ERROR: $${FILE} not found; run 'make package' first"; exit 1; fi; \
		if command -v code >/dev/null 2>&1; then \
			code --install-extension "$${FILE}" || exit 1; \
		elif command -v code-insiders >/dev/null 2>&1; then \
			code-insiders --install-extension "$${FILE}" || exit 1; \
		else \
			echo "ERROR: 'code' CLI not found; please install VS Code CLI or install the .vsix manually: $${FILE}"; exit 1; \
		fi

# package-uninstall: uninstall the .vsix from VS Code
package-uninstall:
	@echo "++ Uninstalling package ..."
	@echo
	@NAME=$(shell node -e "console.log(require('./package.json').name)"); \
	PUBLISHER=$(shell node -e "console.log(require('./package.json').publisher)"); \
	ID=$${PUBLISHER}.$${NAME}; \
	if command -v code >/dev/null 2>&1; then \
		if code --list-extensions | grep -xq "$${ID}"; then \
			code --uninstall-extension "$${ID}" || exit 1; \
			echo "Uninstalled $${ID}"; \
		else \
			echo "Extension $${ID} is not installed"; \
		fi; \
	elif command -v code-insiders >/dev/null 2>&1; then \
		if code-insiders --list-extensions | grep -xq "$${ID}"; then \
			code-insiders --uninstall-extension "$${ID}" || exit 1; \
			echo "Uninstalled $${ID}"; \
		else \
			echo "Extension $${ID} is not installed"; \
		fi; \
	else \
		echo "ERROR: 'code' CLI not found; please uninstall the extension manually: $${ID}"; exit 1; \
	fi

test:
	@echo "++ Running tests ..."
	@echo
	@echo $(MAKE) -C ../tests tests
	@echo
	@$(MAKE) -C ../tests tests
	@echo

tests: test