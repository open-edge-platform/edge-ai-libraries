# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# default goal to show help
.DEFAULT_GOAL := help

# these targets don't create files, so are marked PHONY
.PHONY: help build test lint clean clean-all

# Shell config variable
SHELL	    := bash -eu -o pipefail

### configuration variables ###
# project configuration
PROJECT_NAME  := plcopen-motion-cntrol-docs
VERSION       := $(shell cat VERSION) # read from VERSION file

# Path variables
OUT_DIR       := out
CI_DIR        := ci  # created inside this repo when running in CI, causes some lint to fail

# If out dir doesn't exist, create it
$(OUT_DIR):
	mkdir -p $(OUT_DIR)

### check targets ###
# Python virtualenv, for python-based tools
VENV_DIR     := venv_$(PROJECT_NAME)

# virtualenv activate script has undefined variables, disable then re-enable in bash
$(VENV_DIR): docs/requirements.txt
	python3 -m venv $@ ;\
  set +u; . ./$@/bin/activate; set -u ;\
  python -m pip install --upgrade pip ;\
  python -m pip install -r docs/requirements.txt

check: | $(VENV_DIR) ## Check for and/or install prerequisite tools

# Eventually we want:
# lint: license yamllint pylint black doc8 sphinx-spelling sphinx-linkcheck markdownlint ## Lint all tooling and docs

# But for now, turn off format, spelling, link checks
lint: license yamllint pylint black doc8 sphinx-spelling markdownlint ## Lint all tooling

license: $(VENV_DIR) ## license check with REUSE tool
	set +u; . ./$</bin/activate; set -u ;\
  reuse --version ;\
  reuse --root . lint

# FIXME: API YAML files should be linted, but are still badly formatted, exclude for now
YAML_FILES := $(shell find . -type f \( -name '*.yaml' -o -name '*.yml' \) -print )
yamllint: $(VENV_DIR) ## lint YAML files
	set +u; . ./$</bin/activate; set -u ;\
  yamllint --version ;\
  yamllint -d '{extends: default, ignore: ["$(VENV_DIR)", "$(CI_DIR)", "$(OUT_DIR)", "docs/api/openapi", "generate/sources"]}' -s $(YAML_FILES)

pylint: $(VENV_DIR) ## lint python files
	set +u; . ./$</bin/activate; set -u ;\
	pylint --version ;\
	pylint --ignore "docconf,$(VENV_DIR),$(CI_DIR)" .

black: $(VENV_DIR) ## format check python files
	set +u; . ./$</bin/activate; set -u ;\
	black --version ;\
	black --check .

doc8: $(VENV_DIR) ## lint rst files with doc8
	set +u; . ./$</bin/activate; set -u ;\
	doc8 --version ;\
	doc8 --max-line-length 199 --ignore-path $(VENV_DIR) --ignore-path $(CI_DIR) --ignore-path docconf --ignore-path LICENSES --ignore-path $(OUT_DIR) .

markdownlint: ## lint markdown files
	markdownlint --version ;\
	markdownlint README.md .github/*.md

trivyfsscan: ## run Trivy scan locally
	@echo "Running Trivy scan on the filesystem"
	trivy --version ;\
	trivy fs --scanners vuln,misconfig,secret -s HIGH,CRITICAL .

sphinx-spelling: $(VENV_DIR)
	set +u; . ./$</bin/activate; set -u ;\
    sphinx-build -b spelling "$(SOURCEDIR)" "$(OUT_DIR)/spelling"

build: sphinx-html ## Build all documentation

serve: sphinx-serve ## Serve documentation locally

### cleanup targets ###
clean: ## delete all build artifacts
	rm -rf $(OUT_DIR)

clean-all: clean ## delete all built artifacts and downloaded tools
	rm -rf $(VENV_DIR)

### documentation generation targets ###
generate: docs/shared/shared_iam_groups.rst  ## generate role documentation from config

docs/shared/shared_iam_groups.rst: $(VENV_DIR) generate/role_docs.py generate/sources/platform-keycloak.yaml generate/sources/keycloak-tenant-controller.tpl generate/sources/iam_details.yaml generate/templates/shared_iam_groups.rst.j2
	set +u;	. ./$</bin/activate; set -u ;\
  generate/role_docs.py generate/sources/platform-keycloak.yaml generate/sources/keycloak-tenant-controller.tpl $@ docs/shared/group_role_xy.csv ;\
  doc8 $@

### Sphinx-specific targets ###
SPHINXBUILD   := sphinx-build
SOURCEDIR     := docs/

sphinx-serve: $(VENV_DIR) $(OUT_DIR)
	set +u;	. ./$</bin/activate; set -u ;\
	sphinx-autobuild "${SOURCEDIR}" "${OUT_DIR}"

sphinx-%: $(VENV_DIR) $(OUT_DIR)
	set +u;	. ./$</bin/activate; set -u ;\
	$(SPHINXBUILD) -M $* "$(SOURCEDIR)" "$(OUT_DIR)" -W


listrefs: $(VENV_DIR) $(OUT_DIR) ## list all sphinx references
	set +u;	. ./$</bin/activate; set -u ;\
	python -m sphinx.ext.intersphinx $(OUT_DIR)/html/objects.inv

### help target ###
help: ## Print help for each target
	@echo $(PROJECT_NAME) make targets
	@echo "Target               Makefile:Line    Description"
	@echo "-------------------- ---------------- -----------------------------------------"
	@grep -H -n '^[[:alnum:]_-]*:.* ##' $(MAKEFILE_LIST) \
    | sort -t ":" -k 3 \
    | awk 'BEGIN  {FS=":"}; {sub(".* ## ", "", $$4)}; {printf "%-20s %-16s %s\n", $$3, $$1 ":" $$2, $$4};'
