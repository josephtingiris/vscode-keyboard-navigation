
.DEFAULT_GOAL := help
.PHONY: help all build test tests clean package-install package-uninstall

# default: show help
help:
	@echo "Extension Makefile - Available Targets:"
	@echo "  help            		- show this message (default)"
	@echo "  all             		- clean, build, test, package (delegates)"
	@echo "  build           		- run extension build steps (none by default)"
	@echo "  test            		- run extension tests (delegates to ../tests)"
	@echo "  tests           		- alias for test"
	@echo "  package         		- package extension into .vsix (dist/)"
	@echo "  package-install 		- install the generated .vsix into VS Code"
	@echo "  package-uninstall 		- uninstall the extension from VS Code"

all: clean build test package

build:
	@echo "Extension: no build steps defined"

clean:
	@echo "Cleaning extension artifacts ..."
	# remove test-created mock vscode module placed under project node_modules
	-@rm -rf ../node_modules/vscode
	# remove any other temporary files
	-@rm -rf node_modules .cache tmp

# derives the filename from package.json `name` and `version` (dist/<name>-<version>.vsix)
package:
	@echo "Packaging extension artifacts ..."
	vsce package --allow-missing-repository --out dist/

# package-install: install the .vsix produced into VS Code
package-install:
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
	@echo "Running extension tests ..."
	# delegate to repository-level tests/ Makefile
	@$(MAKE) -C ../tests tests

# alias `make tests` to `make test`
tests: test